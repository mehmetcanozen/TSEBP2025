import { User } from "@prisma/client";

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
}

export interface UserResponse {
  id: string;
  email: string;
  username: string;
  name: string;
  full_name: string | null;
  bio: string | null;
  photo_uri: string | null;
  is_active: boolean;
  is_admin: boolean;
  created_at: Date;
}

export interface AuthenticatedRequest {
  user: User;
  accessToken?: string;
}

export const toUserResponse = (user: User): UserResponse => {
  const fallbackName = user.fullName ?? user.username ?? user.email.split("@")[0] ?? "User";
  return {
    id: user.id,
    email: user.email,
    username: user.username ?? fallbackName,
    name: fallbackName,
    full_name: user.fullName,
    bio: user.bio,
    photo_uri: user.photoUri,
    is_active: user.isActive,
    is_admin: user.isAdmin,
    created_at: user.createdAt,
  };
};
