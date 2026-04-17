import React, { useState, useContext } from 'react';
import { StyleSheet, Text, View, TextInput, TouchableOpacity, KeyboardAvoidingView, Platform, Alert, ScrollView, Image } from 'react-native';
import { AuthContext } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import { LinearGradient } from 'expo-linear-gradient';

export default function SignupScreen({ navigation }: { navigation: any }) {
    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const { signup } = useContext(AuthContext);
    const { colors, isDarkMode } = useTheme();

    const handleSignup = async () => {
        if (!name || !email || !password) {
            Alert.alert('Error', 'Please fill in all fields');
            return;
        }

        try {
            await signup(name, email, password);
            Alert.alert('Success', 'Account created successfully. Please login.');
            navigation.navigate('Login');
        } catch (e) {
            Alert.alert('Signup Failed', (e as Error).message);
        }
    };

    return (
        <KeyboardAvoidingView
            behavior={Platform.OS === "ios" ? "padding" : "height"}
            style={[styles.container, { backgroundColor: colors.background }]}
        >
            {/* Background Decorative Shapes */}
            <View style={[styles.shape1, { backgroundColor: colors.primary, opacity: 0.25 }]} />
            <View style={[styles.shape2, { backgroundColor: colors.headerGradientEnd || '#FF5722', opacity: 0.15 }]} />
            <View style={[styles.shape3, { backgroundColor: colors.primary, opacity: 0.3 }]} />

            <ScrollView contentContainerStyle={styles.scrollContent} bounces={false} keyboardShouldPersistTaps="handled">
                <View style={styles.headerWrapper}>
                    <LinearGradient
                        colors={[colors.headerGradientStart || '#1E3A8A', colors.headerGradientEnd || '#8B5CF6']}
                        start={{ x: 0, y: 0 }}
                        end={{ x: 1, y: 1 }}
                        style={styles.headerBackground}
                    />
                    
                    <View style={styles.headerGreeting}>
                        <Image 
                            source={require('../../assets/fav.png')} 
                            style={styles.logo}
                            resizeMode="contain"
                        />
                        <Text style={styles.greetingTitle}>Create Account</Text>
                        <Text style={styles.greetingSubtitle}>Sign up to get started</Text>
                    </View>
                </View>

                <View style={styles.contentWrapper}>
                    <View style={[styles.card, { backgroundColor: isDarkMode ? 'rgba(42, 26, 24, 0.88)' : 'rgba(255, 255, 255, 0.88)' }]}>
                        <View style={styles.inputGroup}>
                            <Text style={[styles.label, { color: colors.text }]}>Full Name</Text>
                            <TextInput
                                style={[
                                    styles.input, 
                                    { backgroundColor: colors.inputBackground, borderColor: colors.border, color: colors.text }
                                ]}
                                placeholder="Enter your full name"
                                placeholderTextColor={colors.textSecondary}
                                value={name}
                                onChangeText={setName}
                            />
                        </View>

                        <View style={styles.inputGroup}>
                            <Text style={[styles.label, { color: colors.text }]}>Email</Text>
                            <TextInput
                                style={[
                                    styles.input, 
                                    { backgroundColor: colors.inputBackground, borderColor: colors.border, color: colors.text }
                                ]}
                                placeholder="Enter your email"
                                placeholderTextColor={colors.textSecondary}
                                value={email}
                                onChangeText={setEmail}
                                autoCapitalize="none"
                                keyboardType="email-address"
                            />
                        </View>

                        <View style={styles.inputGroup}>
                            <Text style={[styles.label, { color: colors.text }]}>Password</Text>
                            <TextInput
                                style={[
                                    styles.input, 
                                    { backgroundColor: colors.inputBackground, borderColor: colors.border, color: colors.text }
                                ]}
                                placeholder="Create a password"
                                placeholderTextColor={colors.textSecondary}
                                value={password}
                                onChangeText={setPassword}
                                secureTextEntry
                            />
                        </View>

                        <TouchableOpacity 
                            style={[styles.button, { backgroundColor: colors.primary }]} 
                            onPress={handleSignup}
                            activeOpacity={0.8}
                        >
                            <Text style={styles.buttonText}>Sign Up</Text>
                        </TouchableOpacity>

                        <View style={styles.footer}>
                            <Text style={[styles.footerText, { color: colors.textSecondary }]}>Already have an account? </Text>
                            <TouchableOpacity onPress={() => navigation.navigate('Login')} activeOpacity={0.6}>
                                <Text style={[styles.link, { color: colors.primary }]}>Login</Text>
                            </TouchableOpacity>
                        </View>
                    </View>
                </View>
            </ScrollView>
        </KeyboardAvoidingView>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        position: 'relative',
    },
    shape1: {
        position: 'absolute',
        top: '30%',
        left: -50,
        width: 150,
        height: 150,
        borderRadius: 75,
    },
    shape2: {
        position: 'absolute',
        bottom: -30,
        right: -40,
        width: 200,
        height: 200,
        borderRadius: 100,
    },
    shape3: {
        position: 'absolute',
        top: '55%',
        right: -20,
        width: 80,
        height: 80,
        borderRadius: 40,
    },
    scrollContent: {
        flexGrow: 1,
    },
    headerWrapper: {
        width: '100%',
        paddingTop: 80,
        paddingHorizontal: 30,
        paddingBottom: 110,
        borderBottomLeftRadius: 40,
        borderBottomRightRadius: 40,
        overflow: 'hidden',
        borderCurve: 'continuous',
        justifyContent: 'center',
    },
    headerBackground: {
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
    },
    headerGreeting: {
        alignItems: 'center',
    },
    logo: {
        width: 60,
        height: 60,
        marginBottom: 20,
    },
    greetingTitle: {
        color: '#FFF',
        fontSize: 34,
        fontWeight: '800',
        marginBottom: 8,
    },
    greetingSubtitle: {
        color: 'rgba(255,255,255,0.9)',
        fontSize: 16,
        fontWeight: '500',
    },
    contentWrapper: {
        paddingHorizontal: 25,
        marginTop: -60,
    },
    card: {
        borderRadius: 24,
        padding: 25,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 10 },
        shadowOpacity: 0.05,
        shadowRadius: 15,
        elevation: 8,
        borderCurve: 'continuous',
    },
    inputGroup: {
        marginBottom: 20,
    },
    label: {
        fontSize: 14,
        fontWeight: '600',
        marginBottom: 8,
    },
    input: {
        borderWidth: 1,
        borderRadius: 16,
        padding: 16,
        fontSize: 15,
        borderCurve: 'continuous',
    },
    button: {
        borderRadius: 16,
        paddingVertical: 16,
        alignItems: 'center',
        marginTop: 10,
        borderCurve: 'continuous',
    },
    buttonText: {
        color: '#fff',
        fontSize: 16,
        fontWeight: '700',
    },
    footer: {
        flexDirection: 'row',
        justifyContent: 'center',
        marginTop: 24,
    },
    footerText: {
        fontSize: 14,
    },
    link: {
        fontWeight: 'bold',
        fontSize: 14,
    },
});
