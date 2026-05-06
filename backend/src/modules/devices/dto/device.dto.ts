import { IsNotEmpty, IsOptional, IsString, MaxLength } from "class-validator";

export class RegisterDeviceDto {
  @IsString()
  @IsNotEmpty()
  @MaxLength(255)
  device_id!: string;

  @IsString()
  @IsNotEmpty()
  @MaxLength(50)
  platform!: string;

  @IsOptional()
  @IsString()
  @MaxLength(50)
  app_version?: string;
}
