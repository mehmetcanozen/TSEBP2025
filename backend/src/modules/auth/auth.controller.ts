import { Body, Controller, Get, Inject, Post, Put, UseGuards } from "@nestjs/common";
import { User } from "@prisma/client";
import { AuthService } from "./auth.service";
import { BearerAuthGuard } from "./bearer-auth.guard";
import { CurrentUser } from "./current-user.decorator";
import { ChangePasswordDto, LoginDto, ProfileUpdateDto, RefreshDto, RegisterDto } from "./dto/auth.dto";
import { toUserResponse } from "./auth.types";

@Controller("api/v1/auth")
export class AuthController {
  constructor(@Inject(AuthService) private readonly auth: AuthService) {}

  @Post("register")
  async register(@Body() body: RegisterDto) {
    const user = await this.auth.register(body);
    return toUserResponse(user);
  }

  @Post("login")
  async login(@Body() body: LoginDto) {
    return this.auth.login(body);
  }

  @Post("refresh")
  async refresh(@Body() body: RefreshDto) {
    return this.auth.refresh(body.refresh_token);
  }

  @Post("logout")
  async logout(@Body() body: RefreshDto) {
    await this.auth.logout(body.refresh_token);
    return { message: "Logged out." };
  }

  @Get("me")
  @UseGuards(BearerAuthGuard)
  me(@CurrentUser() user: User) {
    return toUserResponse(user);
  }

  @Put("profile")
  @UseGuards(BearerAuthGuard)
  async updateProfile(@CurrentUser() user: User, @Body() body: ProfileUpdateDto) {
    const updated = await this.auth.updateProfile(user.id, body);
    return toUserResponse(updated);
  }

  @Put("change-password")
  @UseGuards(BearerAuthGuard)
  async changePassword(@CurrentUser() user: User, @Body() body: ChangePasswordDto) {
    await this.auth.changePassword(user, body);
    return { message: "Password changed." };
  }
}
