import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import {
  BackendUser,
  clearTokens,
  hasStoredToken,
  loginRequest,
  logoutRequest,
  meRequest,
  registerDesktopDevice,
  signupRequest,
  storeTokens,
  updateProfileRequest,
} from "@/lib/backend-api";

interface User {
  id: string;
  name: string;
  email: string;
  bio: string;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (name: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  updateProfile: (data: Partial<User>) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
};

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const mapUser = (backendUser: BackendUser): User => ({
    id: backendUser.id,
    name: backendUser.full_name ?? backendUser.name ?? backendUser.username,
    email: backendUser.email,
    bio: backendUser.bio ?? "",
  });

  useEffect(() => {
    const restore = async () => {
      try {
        if (!hasStoredToken()) {
          return;
        }
        const backendUser = await meRequest();
        setUser(mapUser(backendUser));
        await registerDesktopDevice();
      } catch {
        clearTokens();
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    };

    void restore();
  }, []);

  const login = async (email: string, password: string) => {
    const tokens = await loginRequest(email, password);
    storeTokens(tokens);
    const backendUser = await meRequest();
    setUser(mapUser(backendUser));
    await registerDesktopDevice();
  };

  const signup = async (name: string, email: string, password: string) => {
    await signupRequest(name, email, password);
    await login(email, password);
  };

  const logout = async () => {
    await logoutRequest();
    clearTokens();
    setUser(null);
  };

  const updateProfile = async (data: Partial<User>) => {
    const backendUser = await updateProfileRequest({ name: data.name, bio: data.bio });
    setUser(mapUser(backendUser));
  };

  return (
    <AuthContext.Provider value={{ user, isLoading, login, signup, logout, updateProfile }}>
      {children}
    </AuthContext.Provider>
  );
};
