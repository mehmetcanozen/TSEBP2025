import { CanActivate, ExecutionContext, Inject, Injectable, UnauthorizedException } from "@nestjs/common";
import { AuthService } from "./auth.service";
import { AuthenticatedRequest } from "./auth.types";

@Injectable()
export class BearerAuthGuard implements CanActivate {
  constructor(@Inject(AuthService) private readonly auth: AuthService) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const request = context.switchToHttp().getRequest<AuthenticatedRequest & { headers: Record<string, string | undefined> }>();
    const header = request.headers.authorization ?? request.headers.Authorization;

    if (!header?.startsWith("Bearer ")) {
      throw new UnauthorizedException("Missing bearer token.");
    }

    const token = header.slice("Bearer ".length).trim();
    const user = await this.auth.verifyAccessToken(token);
    request.user = user;
    request.accessToken = token;
    return true;
  }
}
