import { Body, Controller, Inject, Post, UseGuards } from "@nestjs/common";
import { User } from "@prisma/client";
import { BearerAuthGuard } from "../auth/bearer-auth.guard";
import { CurrentUser } from "../auth/current-user.decorator";
import { RegisterDeviceDto } from "./dto/device.dto";
import { DevicesService } from "./devices.service";

@Controller("api/v1/devices")
@UseGuards(BearerAuthGuard)
export class DevicesController {
  constructor(@Inject(DevicesService) private readonly devices: DevicesService) {}

  @Post("register")
  async register(@CurrentUser() user: User, @Body() body: RegisterDeviceDto) {
    await this.devices.register(user.id, body);
    return { message: "Device registered." };
  }
}
