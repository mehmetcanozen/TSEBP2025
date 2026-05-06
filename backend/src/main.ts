import "reflect-metadata";
import { ValidationPipe } from "@nestjs/common";
import { ConfigService } from "@nestjs/config";
import { NestFactory } from "@nestjs/core";
import { AppModule } from "./app.module";

const parseOrigins = (value?: string): string[] => {
  if (!value) {
    return ["http://localhost:1420", "http://localhost:5173", "http://localhost:8080"];
  }
  return value
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean);
};

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  const config = app.get(ConfigService);

  app.enableCors({
    origin: parseOrigins(config.get<string>("CORS_ORIGINS")),
    credentials: true,
    allowedHeaders: ["Content-Type", "Authorization"],
    methods: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
  });

  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      transform: true,
      forbidNonWhitelisted: true,
    }),
  );

  const port = Number(config.get<string>("PORT") ?? 4000);
  await app.listen(port, "0.0.0.0");
}

void bootstrap();
