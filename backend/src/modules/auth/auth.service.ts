import {
  BadRequestException,
  ConflictException,
  Inject,
  Injectable,
  InternalServerErrorException,
  UnauthorizedException,
} from "@nestjs/common";
import { ConfigService } from "@nestjs/config";
import { AuthProvider, Prisma, User } from "@prisma/client";
import { createHash, randomUUID } from "crypto";
import jwt, { JwtHeader, JwtPayload, SigningKeyCallback } from "jsonwebtoken";
import jwksClient, { JwksClient } from "jwks-rsa";
import { createClient, SupabaseClient } from "@supabase/supabase-js";
import bcrypt from "bcryptjs";
import { PrismaService } from "../../shared/prisma/prisma.service";
import { authFailed, conflictFromUniqueError, isUniqueConstraintError } from "../../shared/http/api-error";
import { ChangePasswordDto, LoginDto, ProfileUpdateDto, RegisterDto } from "./dto/auth.dto";
import { TokenResponse } from "./auth.types";

type AuthMode = "local" | "supabase";

interface SupabaseClaims extends JwtPayload {
  email?: string;
  user_metadata?: Record<string, unknown>;
}

@Injectable()
export class AuthService {
  private supabasePublic?: SupabaseClient;
  private supabaseAdmin?: SupabaseClient;
  private supabaseJwks?: JwksClient;

  constructor(
    @Inject(PrismaService) private readonly prisma: PrismaService,
    @Inject(ConfigService) private readonly config: ConfigService,
  ) {}

  async register(dto: RegisterDto): Promise<User> {
    return this.authMode() === "supabase" ? this.registerWithSupabase(dto) : this.registerLocal(dto);
  }

  async login(dto: LoginDto): Promise<TokenResponse> {
    return this.authMode() === "supabase" ? this.loginWithSupabase(dto) : this.loginLocal(dto);
  }

  async refresh(refreshToken: string): Promise<TokenResponse> {
    return this.authMode() === "supabase"
      ? this.refreshSupabase(refreshToken)
      : this.refreshLocal(refreshToken);
  }

  async logout(refreshToken: string): Promise<void> {
    if (this.authMode() === "local") {
      await this.prisma.refreshToken.updateMany({
        where: { tokenHash: this.tokenHash(refreshToken), revokedAt: null },
        data: { revokedAt: new Date() },
      });
      return;
    }
    await this.logoutSupabase(refreshToken);
  }

  async verifyAccessToken(token: string): Promise<User> {
    return this.authMode() === "supabase"
      ? this.verifySupabaseAccessToken(token)
      : this.verifyLocalAccessToken(token);
  }

  async updateProfile(userId: string, dto: ProfileUpdateDto): Promise<User> {
    return this.prisma.user.update({
      where: { id: userId },
      data: {
        fullName: dto.full_name ?? dto.name,
        bio: dto.bio,
        photoUri: dto.photo_uri,
      },
    });
  }

  async changePassword(user: User, dto: ChangePasswordDto): Promise<void> {
    if (this.authMode() === "supabase") {
      await this.changeSupabasePassword(user, dto);
      return;
    }

    if (!user.passwordHash || !(await bcrypt.compare(dto.old_password, user.passwordHash))) {
      throw new BadRequestException("Current password is incorrect.");
    }

    await this.prisma.$transaction([
      this.prisma.user.update({
        where: { id: user.id },
        data: { passwordHash: await bcrypt.hash(dto.new_password, 12) },
      }),
      this.prisma.refreshToken.updateMany({
        where: { userId: user.id, revokedAt: null },
        data: { revokedAt: new Date() },
      }),
    ]);
  }

  private async registerLocal(dto: RegisterDto): Promise<User> {
    const email = dto.email.trim().toLowerCase();
    const username = this.normalizeUsername(dto.username ?? dto.name ?? email.split("@")[0]);
    const fullName = dto.full_name ?? dto.name ?? username;

    try {
      return await this.prisma.user.create({
        data: {
          authProvider: AuthProvider.LOCAL,
          authSubject: randomUUID(),
          email,
          username,
          fullName,
          passwordHash: await bcrypt.hash(dto.password, 12),
        },
      });
    } catch (error) {
      if (isUniqueConstraintError(error)) {
        throw conflictFromUniqueError(error);
      }
      throw error;
    }
  }

  private async loginLocal(dto: LoginDto): Promise<TokenResponse> {
    const user = await this.prisma.user.findUnique({
      where: { email: dto.email.trim().toLowerCase() },
    });

    if (!user?.passwordHash || !(await bcrypt.compare(dto.password, user.passwordHash))) {
      throw authFailed();
    }
    if (!user.isActive) {
      throw new UnauthorizedException("Account is disabled.");
    }

    return this.issueLocalTokens(user.id);
  }

  private async refreshLocal(refreshToken: string): Promise<TokenResponse> {
    const payload = this.verifyLocalJwt(refreshToken);
    if (payload.type !== "refresh" || !payload.sub) {
      throw new UnauthorizedException("Invalid refresh token.");
    }

    const tokenHash = this.tokenHash(refreshToken);
    const stored = await this.prisma.refreshToken.findUnique({ where: { tokenHash } });
    if (!stored || stored.revokedAt || stored.expiresAt <= new Date()) {
      throw new UnauthorizedException("Refresh token is expired or revoked.");
    }

    await this.prisma.refreshToken.update({
      where: { id: stored.id },
      data: { revokedAt: new Date() },
    });
    return this.issueLocalTokens(payload.sub);
  }

  private async issueLocalTokens(userId: string): Promise<TokenResponse> {
    const accessSecret = this.localJwtSecret();
    const accessToken = jwt.sign(
      { sub: userId, type: "access" },
      accessSecret,
      {
        expiresIn: this.numberConfig("LOCAL_ACCESS_TOKEN_SECONDS", 900),
        issuer: "tsebp2025-backend",
        audience: "tsebp2025-clients",
      },
    );

    const refreshDays = this.numberConfig("LOCAL_REFRESH_TOKEN_DAYS", 30);
    const refreshToken = jwt.sign(
      { sub: userId, type: "refresh", jti: randomUUID() },
      accessSecret,
      {
        expiresIn: `${refreshDays}d`,
        issuer: "tsebp2025-backend",
        audience: "tsebp2025-clients",
      },
    );

    await this.prisma.refreshToken.create({
      data: {
        userId,
        tokenHash: this.tokenHash(refreshToken),
        expiresAt: new Date(Date.now() + refreshDays * 24 * 60 * 60 * 1000),
      },
    });

    return {
      access_token: accessToken,
      refresh_token: refreshToken,
      token_type: "bearer",
    };
  }

  private async verifyLocalAccessToken(token: string): Promise<User> {
    const payload = this.verifyLocalJwt(token);
    if (payload.type !== "access" || !payload.sub) {
      throw new UnauthorizedException("Invalid access token.");
    }

    const user = await this.prisma.user.findUnique({ where: { id: payload.sub } });
    if (!user?.isActive) {
      throw new UnauthorizedException("User not found.");
    }
    return user;
  }

  private verifyLocalJwt(token: string): JwtPayload & { type?: string } {
    try {
      return jwt.verify(token, this.localJwtSecret(), {
        issuer: "tsebp2025-backend",
        audience: "tsebp2025-clients",
      }) as JwtPayload & { type?: string };
    } catch {
      throw new UnauthorizedException("Invalid token.");
    }
  }

  private async registerWithSupabase(dto: RegisterDto): Promise<User> {
    const email = dto.email.trim().toLowerCase();
    const username = this.normalizeUsername(dto.username ?? dto.name ?? email.split("@")[0]);
    const fullName = dto.full_name ?? dto.name ?? username;
    const metadata = { username, full_name: fullName };
    const admin = this.getSupabaseAdminOrNull();

    const result = admin
      ? await admin.auth.admin.createUser({
          email,
          password: dto.password,
          email_confirm: true,
          user_metadata: metadata,
        })
      : await this.getSupabasePublic().auth.signUp({
          email,
          password: dto.password,
          options: { data: metadata },
        });

    if (result.error || !result.data.user) {
      throw new ConflictException(result.error?.message ?? "Supabase registration failed.");
    }

    return this.upsertSupabaseUser(
      result.data.user.id,
      result.data.user.email ?? email,
      username,
      fullName,
    );
  }

  private async loginWithSupabase(dto: LoginDto): Promise<TokenResponse> {
    const result = await this.getSupabasePublic().auth.signInWithPassword({
      email: dto.email.trim().toLowerCase(),
      password: dto.password,
    });

    if (result.error || !result.data.session || !result.data.user) {
      throw authFailed();
    }

    const metadata = result.data.user.user_metadata ?? {};
    await this.upsertSupabaseUser(
      result.data.user.id,
      result.data.user.email ?? dto.email,
      this.normalizeUsername(String(metadata.username ?? result.data.user.email?.split("@")[0] ?? "user")),
      String(metadata.full_name ?? metadata.name ?? metadata.username ?? ""),
      false,
    );

    return {
      access_token: result.data.session.access_token,
      refresh_token: result.data.session.refresh_token,
      token_type: "bearer",
    };
  }

  private async refreshSupabase(refreshToken: string): Promise<TokenResponse> {
    const result = await this.getSupabasePublic().auth.refreshSession({ refresh_token: refreshToken });
    if (result.error || !result.data.session) {
      throw new UnauthorizedException(result.error?.message ?? "Invalid refresh token.");
    }
    return {
      access_token: result.data.session.access_token,
      refresh_token: result.data.session.refresh_token,
      token_type: "bearer",
    };
  }

  private async logoutSupabase(refreshToken: string): Promise<void> {
    const tokens = await this.refreshSupabase(refreshToken);
    const { error } = await this.getSupabasePublic().auth.admin.signOut(tokens.access_token, "local");
    if (error) {
      throw new UnauthorizedException(error.message);
    }
  }

  private async verifySupabaseAccessToken(token: string): Promise<User> {
    const payload = await this.verifySupabaseJwt(token);
    if (!payload.sub) {
      throw new UnauthorizedException("Supabase token is missing subject.");
    }

    const metadata = payload.user_metadata ?? {};
    return this.upsertSupabaseUser(
      payload.sub,
      payload.email ?? `${payload.sub}@supabase.local`,
      this.normalizeUsername(String(metadata.username ?? payload.email?.split("@")[0] ?? payload.sub.slice(0, 12))),
      String(metadata.full_name ?? metadata.name ?? metadata.username ?? ""),
      false,
    );
  }

  private async verifySupabaseJwt(token: string): Promise<SupabaseClaims> {
    const jwtSecret = this.config.get<string>("SUPABASE_JWT_SECRET");
    const audience = this.config.get<string>("SUPABASE_JWT_AUDIENCE") || undefined;

    try {
      if (jwtSecret) {
        return jwt.verify(token, jwtSecret, audience ? { audience } : undefined) as SupabaseClaims;
      }

      const decoded = await new Promise<JwtPayload | string>((resolve, reject) => {
        jwt.verify(
          token,
          (header: JwtHeader, callback: SigningKeyCallback) => {
            if (!header.kid) {
              callback(new Error("Supabase JWT is missing kid."));
              return;
            }
            this.getSupabaseJwks().getSigningKey(header.kid, (error, key) => {
              callback(error, key?.getPublicKey());
            });
          },
          audience ? { audience } : undefined,
          (error, verified) => {
            if (error || !verified) {
              reject(error ?? new Error("JWT verification failed."));
              return;
            }
            resolve(verified);
          },
        );
      });

      if (typeof decoded === "string") {
        throw new Error("Unexpected string JWT payload.");
      }
      return decoded as SupabaseClaims;
    } catch {
      throw new UnauthorizedException("Invalid Supabase token.");
    }
  }

  private async changeSupabasePassword(user: User, dto: ChangePasswordDto): Promise<void> {
    const signIn = await this.getSupabasePublic().auth.signInWithPassword({
      email: user.email,
      password: dto.old_password,
    });
    if (signIn.error) {
      throw new BadRequestException("Current password is incorrect.");
    }

    const admin = this.getSupabaseAdminOrNull();
    if (!admin) {
      throw new BadRequestException("Supabase password changes require SUPABASE_SERVICE_ROLE_KEY.");
    }

    const result = await admin.auth.admin.updateUserById(user.authSubject, {
      password: dto.new_password,
    });
    if (result.error) {
      throw new BadRequestException(result.error.message);
    }
  }

  private async upsertSupabaseUser(
    authSubject: string,
    email: string,
    username: string,
    fullName: string,
    overwriteProfileFields = true,
  ): Promise<User> {
    const updateData: Prisma.UserUpdateInput = {
      email: email.toLowerCase(),
      isActive: true,
    };
    if (overwriteProfileFields) {
      updateData.username = username;
      updateData.fullName = fullName || username;
    }

    try {
      return await this.prisma.user.upsert({
        where: {
          authProvider_authSubject: {
            authProvider: AuthProvider.SUPABASE,
            authSubject,
          },
        },
        create: {
          authProvider: AuthProvider.SUPABASE,
          authSubject,
          email: email.toLowerCase(),
          username,
          fullName: fullName || username,
        },
        update: updateData,
      });
    } catch (error) {
      if (error instanceof Prisma.PrismaClientKnownRequestError && error.code === "P2002") {
        const existing = await this.prisma.user.findUnique({ where: { email: email.toLowerCase() } });
        if (existing) {
          const existingUpdateData: Prisma.UserUpdateInput = {
            authProvider: AuthProvider.SUPABASE,
            authSubject,
            isActive: true,
          };
          if (overwriteProfileFields) {
            existingUpdateData.username = username;
            existingUpdateData.fullName = fullName || username;
          }
          return this.prisma.user.update({
            where: { id: existing.id },
            data: existingUpdateData,
          });
        }
      }
      throw error;
    }
  }

  private authMode(): AuthMode {
    const mode = (this.config.get<string>("AUTH_PROVIDER") ?? "local").toLowerCase();
    if (mode !== "local" && mode !== "supabase") {
      throw new InternalServerErrorException(`Unsupported AUTH_PROVIDER: ${mode}`);
    }
    return mode;
  }

  private getSupabasePublic(): SupabaseClient {
    if (!this.supabasePublic) {
      this.supabasePublic = createClient(this.required("SUPABASE_URL"), this.required("SUPABASE_ANON_KEY"), {
        auth: {
          persistSession: false,
          autoRefreshToken: false,
          detectSessionInUrl: false,
        },
      });
    }
    return this.supabasePublic;
  }

  private getSupabaseAdminOrNull(): SupabaseClient | null {
    const key = this.config.get<string>("SUPABASE_SERVICE_ROLE_KEY");
    if (!key) {
      return null;
    }
    if (!this.supabaseAdmin) {
      this.supabaseAdmin = createClient(this.required("SUPABASE_URL"), key, {
        auth: {
          persistSession: false,
          autoRefreshToken: false,
          detectSessionInUrl: false,
        },
      });
    }
    return this.supabaseAdmin;
  }

  private getSupabaseJwks(): JwksClient {
    if (!this.supabaseJwks) {
      const url = this.required("SUPABASE_URL").replace(/\/$/, "");
      this.supabaseJwks = jwksClient({
        jwksUri: `${url}/auth/v1/.well-known/jwks.json`,
        cache: true,
        cacheMaxEntries: 5,
        cacheMaxAge: 10 * 60 * 1000,
      });
    }
    return this.supabaseJwks;
  }

  private localJwtSecret(): string {
    const value = this.config.get<string>("LOCAL_JWT_SECRET");
    if (value && value.length >= 32) {
      return value;
    }
    if (this.config.get<string>("NODE_ENV") === "production") {
      throw new InternalServerErrorException("LOCAL_JWT_SECRET must be set in production.");
    }
    return "development-only-tsebp2025-local-secret-change-me";
  }

  private required(key: string): string {
    const value = this.config.get<string>(key);
    if (!value) {
      throw new InternalServerErrorException(`${key} is required.`);
    }
    return value;
  }

  private numberConfig(key: string, fallback: number): number {
    const value = Number(this.config.get<string>(key));
    return Number.isFinite(value) && value > 0 ? value : fallback;
  }

  private normalizeUsername(value: string): string {
    const normalized = value
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_-]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 50);

    if (normalized.length >= 3) {
      return normalized;
    }
    return `user_${randomUUID().slice(0, 8)}`;
  }

  private tokenHash(token: string): string {
    return createHash("sha256").update(token).digest("hex");
  }
}
