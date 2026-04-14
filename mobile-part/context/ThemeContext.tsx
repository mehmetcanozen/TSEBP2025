import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useColorScheme } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

type Theme = 'light' | 'dark';

interface ThemeContextType {
    theme: Theme;
    isDarkMode: boolean;
    toggleTheme: () => void;
    colors: {
        background: string;
        text: string;
        card: string;
        border: string;
        primary: string;
        textSecondary: string;
        inputBackground: string;
        headerGradientStart: string;
        headerGradientEnd: string;
    };
}

export const lightColors = {
    background: '#F8FAFC',
    text: '#0F172A',
    card: '#FFFFFF',
    border: '#E2E8F0',
    primary: '#6D28D9', // Violet/Purple (Morumsu)
    textSecondary: '#64748B',
    inputBackground: '#F1F5F9',
    headerGradientStart: '#1E3A8A', // Navy Blue / Lacivert
    headerGradientEnd: '#8B5CF6', // Purple / Mor
};

export const darkColors = {
    background: '#0B0F19', // Very dark blue
    text: '#F8FAFC',
    card: '#1E293B',
    border: '#334155',
    primary: '#8B5CF6', // Bright Purple / Açık Mor
    textSecondary: '#94A3B8',
    inputBackground: '#0F172A',
    headerGradientStart: '#0F172A', // Deep Navy / Koyu Lacivert
    headerGradientEnd: '#7C3AED', // Deep Purple / Koyu Mor
};

export const AppThemeContext = createContext<ThemeContextType>({} as ThemeContextType);

export const ThemeProvider = ({ children }: { children: ReactNode }) => {
    const systemScheme = useColorScheme();
    const [theme, setTheme] = useState<Theme>('light');

    useEffect(() => {
        loadTheme();
    }, []);

    const loadTheme = async () => {
        try {
            const savedTheme = await AsyncStorage.getItem('APP_THEME');
            if (savedTheme) {
                setTheme(savedTheme as Theme);
            } else if (systemScheme) {
                setTheme(systemScheme);
            }
        } catch (e) {
            console.log('Failed to load theme', e);
        }
    };

    const toggleTheme = async () => {
        const newTheme = theme === 'light' ? 'dark' : 'light';
        setTheme(newTheme);
        await AsyncStorage.setItem('APP_THEME', newTheme);
    };

    const colors = theme === 'dark' ? darkColors : lightColors;

    return (
        <AppThemeContext.Provider value={{ theme, isDarkMode: theme === 'dark', toggleTheme, colors }}>
            {children}
        </AppThemeContext.Provider>
    );
};

export const useTheme = () => useContext(AppThemeContext);
