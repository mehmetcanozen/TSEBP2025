import React, { createContext, useState, useEffect, useContext, ReactNode } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { api } from '../services/api';

interface AuthContextType {
    isLoading: boolean;
    userToken: string | null;
    userInfo: any | null;
    login: (email: string, password: string) => Promise<void>;
    signup: (name: string, email: string, password: string) => Promise<void>;
    logout: () => Promise<void>;
    updateProfile: (name: string, bio: string, photoUri?: string) => Promise<void>;
}

export const AuthContext = createContext<AuthContextType>({} as AuthContextType);

const ACCESS_TOKEN_KEY = 'ACCESS_TOKEN';
const REFRESH_TOKEN_KEY = 'REFRESH_TOKEN';
const USER_INFO_KEY = 'USER_INFO';

export const AuthProvider = ({ children }: { children: ReactNode }) => {
    const [isLoading, setIsLoading] = useState(false);
    const [userToken, setUserToken] = useState<string | null>(null);
    const [userInfo, setUserInfo] = useState<any | null>(null);

    const login = async (email: string, password: string) => {
        setIsLoading(true);
        try {
            const response = await api.post('/auth/login', { email, password });
            const { access_token, refresh_token } = response.data;

            // Token'ları kaydet
            await AsyncStorage.setItem(ACCESS_TOKEN_KEY, access_token);
            await AsyncStorage.setItem(REFRESH_TOKEN_KEY, refresh_token);

            // Axios'a Authorization header ekle
            api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;

            // Kullanıcı bilgilerini çek
            const meResponse = await api.get('/auth/me');
            const user = meResponse.data;
            await AsyncStorage.setItem(USER_INFO_KEY, JSON.stringify(user));

            setUserToken(access_token);
            setUserInfo(user);
            console.log('Login success:', user.username);
        } catch (e: any) {
            const message = e?.response?.data?.detail || e?.message || 'Login failed';
            throw new Error(message);
        } finally {
            setIsLoading(false);
        }
    };

    const signup = async (name: string, email: string, password: string) => {
        setIsLoading(true);
        try {
            // Boşlukları alt çizgi ile değiştir (backend validasyonu için)
            const sanitizedUsername = name.trim().replace(/\s+/g, '_');

            await api.post('/auth/register', {
                username: sanitizedUsername,
                email,
                password,
            });
            console.log('Signup success');
        } catch (e: any) {
            const detail = e?.response?.data?.detail;
            let message: string;
            if (Array.isArray(detail)) {
                // FastAPI Pydantic validation hataları dizi döndürür
                message = detail.map((err: any) => err?.msg || JSON.stringify(err)).join('\n');
            } else if (typeof detail === 'string') {
                message = detail;
            } else {
                message = e?.message || 'Signup failed';
            }
            throw new Error(message);
        } finally {
            setIsLoading(false);
        }
    };

    const logout = async () => {
        setIsLoading(true);
        try {
            const refreshToken = await AsyncStorage.getItem(REFRESH_TOKEN_KEY);
            if (refreshToken) {
                await api.post('/auth/logout', { refresh_token: refreshToken }).catch(() => {});
            }
        } catch (_) {}
        finally {
            await AsyncStorage.multiRemove([ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY, USER_INFO_KEY]);
            delete api.defaults.headers.common['Authorization'];
            setUserToken(null);
            setUserInfo(null);
            setIsLoading(false);
        }
    };

    const isLoggedIn = async () => {
        try {
            setIsLoading(true);

            const accessToken = await AsyncStorage.getItem(ACCESS_TOKEN_KEY);
            const userInfoJson = await AsyncStorage.getItem(USER_INFO_KEY);

            if (accessToken && userInfoJson) {
                api.defaults.headers.common['Authorization'] = `Bearer ${accessToken}`;
                setUserToken(accessToken);
                setUserInfo(JSON.parse(userInfoJson));
            }
        } catch (e: any) {
            console.log(`isLoggedIn error: ${e}`);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        isLoggedIn();
    }, []);

    const updateProfile = async (name: string, bio: string, photoUri?: string) => {
        setIsLoading(true);
        try {
            const response = await api.put('/auth/profile', {
                full_name: name,
                bio: bio,
                photo_uri: photoUri,
            });

            const updatedUser = response.data;
            await AsyncStorage.setItem(USER_INFO_KEY, JSON.stringify(updatedUser));
            setUserInfo(updatedUser);
            console.log('Profile updated on backend');
        } catch (e: any) {
            console.log(`Update profile error: ${e}`);
            throw e;
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <AuthContext.Provider value={{ login, logout, signup, updateProfile, isLoading, userToken, userInfo }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);
