import { Module } from "@nestjs/common";
import { ConfigModule } from "@nestjs/config";
import { AuthModule } from "./modules/auth/auth.module";
import { DevicesModule } from "./modules/devices/devices.module";
import { HealthModule } from "./modules/health/health.module";
import { HistoryModule } from "./modules/history/history.module";
import { SettingsModule } from "./modules/settings/settings.module";
import { PrismaModule } from "./shared/prisma/prisma.module";

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    PrismaModule,
    HealthModule,
    AuthModule,
    DevicesModule,
    HistoryModule,
    SettingsModule,
  ],
})
export class AppModule {}
