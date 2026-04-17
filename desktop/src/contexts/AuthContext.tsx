import { createContext, useContext, useState, ReactNode } from "react";

interface User {
  name: string;
  email: string;
  bio: string;
}

interface AuthContextType {
  user: User | null;
  login: (email: string, password: string) => void;
  signup: (name: string, email: string, password: string) => void;
  logout: () => void;
  updateProfile: (data: Partial<User>) => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
};

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);

  const login = (email: string, _password: string) => {
    setUser({ name: email.split("@")[0], email, bio: "" });
  };

  const signup = (name: string, email: string, _password: string) => {
    setUser({ name, email, bio: "" });
  };

  const logout = () => setUser(null);

  const updateProfile = (data: Partial<User>) => {
    setUser(prev => prev ? { ...prev, ...data } : null);
  };

  return (
    <AuthContext.Provider value={{ user, login, signup, logout, updateProfile }}>
      {children}
    </AuthContext.Provider>
  );
};
