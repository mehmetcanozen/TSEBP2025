import { Body, Controller, Get, Inject, Put, UseGuards } from "@nestjs/common";
import { User } from "@prisma/client";
import { BearerAuthGuard } from "../auth/bearer-auth.guard";
import { CurrentUser } from "../auth/current-user.decorator";
import { UpdateSettingsDto } from "./dto/settings.dto";
import { SettingsService } from "./settings.service";

@Controller("api/v1/settings")
@UseGuards(BearerAuthGuard)
export class SettingsController {
  constructor(@Inject(SettingsService) private readonly settings: SettingsService) {}

  @Get()
  get(@CurrentUser() user: User) {
    return this.settings.get(user.id);
  }

  @Put()
  update(@CurrentUser() user: User, @Body() body: UpdateSettingsDto) {
    return this.settings.update(user.id, body.data);
  }
}
