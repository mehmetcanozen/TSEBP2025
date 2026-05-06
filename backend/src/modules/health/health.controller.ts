import { Controller, Get, Inject } from "@nestjs/common";
import { ConfigService } from "@nestjs/config";

@Controller()
export class HealthController {
  constructor(@Inject(ConfigService) private readonly config: ConfigService) {}

  @Get()
  root() {
    return {
      service: "tsebp2025-backend",
      status: "ok",
      api: "/api/v1",
      suppression: "on-device",
    };
  }

  @Get("health")
  health() {
    return {
      status: "ok",
      authProvider: this.config.get<string>("AUTH_PROVIDER") ?? "local",
    };
  }

  @Get("api/v1/health")
  apiHealth() {
    return this.health();
  }
}
