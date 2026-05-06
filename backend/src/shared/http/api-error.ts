import { BadRequestException, ConflictException, UnauthorizedException } from "@nestjs/common";
import { Prisma } from "@prisma/client";

export const isUniqueConstraintError = (error: unknown): error is Prisma.PrismaClientKnownRequestError =>
  error instanceof Prisma.PrismaClientKnownRequestError && error.code === "P2002";

export const conflictFromUniqueError = (error: Prisma.PrismaClientKnownRequestError) => {
  const target = Array.isArray(error.meta?.target) ? error.meta?.target.join(", ") : "field";
  return new ConflictException(`A record already exists for ${target}.`);
};

export const authFailed = () => new UnauthorizedException("Invalid email or password.");

export const badRequest = (message: string) => new BadRequestException(message);
