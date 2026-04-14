import React, { useContext, useState } from 'react';
import { StyleSheet, Text, View, Switch, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons } from '@expo/vector-icons';
import { AuthContext } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { LinearGradient } from 'expo-linear-gradient';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { testBackendConnection } from '../services/api';

export default function SettingsScreen() {
    const { logout, userInfo } = useContext(AuthContext);
    const userEmail = userInfo?.email || "No Email";
    const { isDarkMode, toggleTheme, colors } = useTheme();
    const navigation = useNavigation<any>();

    const [notificationsEnabled, setNotificationsEnabled] = useState(true);
    const [connectionStatus, setConnectionStatus] = useState<'idle' | 'testing' | 'success' | 'error'>('idle');
    const [connectionMessage, setConnectionMessage] = useState('');

    useFocusEffect(
        React.useCallback(() => {
            const loadNotificationPreference = async () => {
                try {
                    const savedValue = await AsyncStorage.getItem('APP_NOTIFICATIONS');
                    if (savedValue !== null) {
                        setNotificationsEnabled(savedValue === 'true');
                    }
                } catch (e) {
                    console.log('Failed to load notification preference', e);
                }
            };
            loadNotificationPreference();
        }, [])
    );

    const toggleNotifications = async () => {
        const newValue = !notificationsEnabled;
        setNotificationsEnabled(newValue);
        await AsyncStorage.setItem('APP_NOTIFICATIONS', String(newValue));
    };

    const handleTestConnection = async () => {
        setConnectionStatus('testing');
        setConnectionMessage('');
        try {
            const data = await testBackendConnection();
            setConnectionStatus('success');
            setConnectionMessage(JSON.stringify(data));
        } catch (error: any) {
            setConnectionStatus('error');
            setConnectionMessage(error?.message || 'Connection failed');
        }
    };

    return (
        <View style={{ flex: 1, backgroundColor: colors.background }}>
            <ScrollView contentContainerStyle={styles.container} bounces={false}>
                <View style={styles.headerWrapper}>
                <LinearGradient
                    colors={[colors.headerGradientStart || '#FF8A00', colors.headerGradientEnd || '#FF5722']}
                    start={{ x: 0, y: 0 }}
                    end={{ x: 1, y: 1 }}
                    style={styles.headerBackground}
                />
                
                <View style={[styles.headerTopBar, {marginTop: 10}]}>
                    <Text style={styles.headerTopText}>App Settings</Text>
                </View>

                <View style={styles.headerGreeting}>
                    <Text style={styles.greetingTitle}>Settings</Text>
                    <Text style={styles.greetingSubtitle}>Preferences & Account control</Text>
                </View>
            </View>

            <View style={styles.contentWrapper}>
                <View style={[styles.card, { backgroundColor: colors.card }]}>
                    <Text style={[styles.sectionTitle, { color: colors.textSecondary }]}>Account</Text>

                    <View style={styles.row}>
                        <View style={[styles.iconContainer, { backgroundColor: isDarkMode ? '#4A5568' : '#FFF0E5' }]}>
                            <Ionicons name="mail" size={20} color={colors.primary} />
                        </View>
                        <View style={styles.rowContent}>
                            <Text style={[styles.label, { color: colors.text }]}>Email</Text>
                            <Text style={[styles.value, { color: colors.textSecondary }]}>{userEmail}</Text>
                        </View>
                    </View>
                    <View style={[styles.separator, { backgroundColor: isDarkMode ? '#3D2D27' : '#FFE0D1' }]} />

                    <TouchableOpacity style={styles.row} activeOpacity={0.7} onPress={() => navigation.navigate('ChangePassword')}>
                        <View style={[styles.iconContainer, { backgroundColor: isDarkMode ? '#4A5568' : '#FFF0E5' }]}>
                            <Ionicons name="lock-closed" size={20} color={colors.primary} />
                        </View>
                        <View style={styles.rowContent}>
                            <Text style={[styles.label, { color: colors.text }]}>Change Password</Text>
                        </View>
                        <Ionicons name="chevron-forward" size={20} color={colors.textSecondary} />
                    </TouchableOpacity>
                </View>

                <View style={[styles.card, { backgroundColor: colors.card }]}>
                    <Text style={[styles.sectionTitle, { color: colors.textSecondary }]}>Preferences</Text>

                    <View style={styles.row}>
                        <View style={[styles.iconContainer, { backgroundColor: isDarkMode ? '#2D3748' : '#EDF2F7' }]}>
                            <Ionicons name="moon" size={20} color={isDarkMode ? '#90CDF4' : '#4A5568'} />
                        </View>
                        <View style={styles.rowContent}>
                            <Text style={[styles.label, { color: colors.text }]}>Dark Mode</Text>
                        </View>
                        <Switch
                            trackColor={{ false: "#CBD5E0", true: colors.primary + '80' }}
                            thumbColor={isDarkMode ? colors.primary : "#FFF"}
                            ios_backgroundColor="#CBD5E0"
                            onValueChange={toggleTheme}
                            value={isDarkMode}
                        />
                    </View>
                    <View style={[styles.separator, { backgroundColor: isDarkMode ? '#3D2D27' : '#FFE0D1' }]} />

                    <View style={styles.row}>
                        <View style={[styles.iconContainer, { backgroundColor: isDarkMode ? '#2D3748' : '#EDF2F7' }]}>
                            <Ionicons name="notifications" size={20} color={isDarkMode ? '#F6AD55' : '#4A5568'} />
                        </View>
                        <View style={styles.rowContent}>
                            <Text style={[styles.label, { color: colors.text }]}>Notifications</Text>
                        </View>
                        <Switch
                            trackColor={{ false: "#CBD5E0", true: colors.primary + '80' }}
                            thumbColor={notificationsEnabled ? colors.primary : "#FFF"}
                            ios_backgroundColor="#CBD5E0"
                            onValueChange={toggleNotifications}
                            value={notificationsEnabled}
                        />
                    </View>
                </View>

                {/* Backend Connection Test */}
                <View style={[styles.card, { backgroundColor: colors.card }]}>
                    <Text style={[styles.sectionTitle, { color: colors.textSecondary }]}>Developer</Text>
                    <TouchableOpacity
                        style={[styles.testButton, { backgroundColor: colors.primary }]}
                        onPress={handleTestConnection}
                        activeOpacity={0.8}
                        disabled={connectionStatus === 'testing'}
                    >
                        {connectionStatus === 'testing' ? (
                            <ActivityIndicator color="#FFF" size="small" />
                        ) : (
                            <Ionicons name="wifi" size={20} color="#FFF" style={{ marginRight: 8 }} />
                        )}
                        <Text style={styles.testButtonText}>
                            {connectionStatus === 'testing' ? 'Testing...' : 'Test Backend Connection'}
                        </Text>
                    </TouchableOpacity>

                    {connectionStatus !== 'idle' && (
                        <View style={[styles.statusBox, {
                            backgroundColor: connectionStatus === 'success'
                                ? (isDarkMode ? '#22543D' : '#F0FFF4')
                                : (isDarkMode ? '#742A2A' : '#FFF5F5')
                        }]}>
                            <Ionicons
                                name={connectionStatus === 'success' ? 'checkmark-circle' : 'close-circle'}
                                size={18}
                                color={connectionStatus === 'success' ? '#38A169' : '#E53E3E'}
                                style={{ marginRight: 8 }}
                            />
                            <Text style={[styles.statusText, {
                                color: connectionStatus === 'success'
                                    ? (isDarkMode ? '#9AE6B4' : '#276749')
                                    : (isDarkMode ? '#FC8181' : '#9B2C2C')
                            }]} numberOfLines={3}>
                                {connectionStatus === 'success'
                                    ? `✅ Connected! ${connectionMessage}`
                                    : `❌ Error: ${connectionMessage}`
                                }
                            </Text>
                        </View>
                    )}
                </View>

                <TouchableOpacity style={styles.logoutButton} onPress={logout} activeOpacity={0.8}>
                    <Ionicons name="log-out-outline" size={22} color="#FFF" style={{marginRight: 8}} />
                    <Text style={styles.logoutButtonText}>Sign Out</Text>
                </TouchableOpacity>
            </View>
            </ScrollView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        flexGrow: 1,
        paddingBottom: 40,
    },
    headerWrapper: {
        width: '100%',
        paddingTop: 50,
        paddingHorizontal: 25,
        paddingBottom: 90,
        borderBottomLeftRadius: 35,
        borderBottomRightRadius: 35,
        overflow: 'hidden',
        borderCurve: 'continuous',
    },
    headerBackground: {
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
    },
    headerTopBar: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 20,
    },
    headerTopText: {
        color: 'rgba(255,255,255,0.8)',
        fontSize: 14,
        fontWeight: '600',
    },
    headerGreeting: {
        marginBottom: 10,
    },
    greetingTitle: {
        color: '#FFF',
        fontSize: 26,
        fontWeight: '700',
    },
    greetingSubtitle: {
        color: 'rgba(255,255,255,0.9)',
        fontSize: 16,
        fontWeight: '500',
        marginTop: 4,
    },
    contentWrapper: {
        paddingHorizontal: 20,
        marginTop: -65,
    },
    card: {
        borderRadius: 24,
        padding: 20,
        marginBottom: 20,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 10 },
        shadowOpacity: 0.05,
        shadowRadius: 15,
        elevation: 8,
        borderCurve: 'continuous',
    },
    sectionTitle: {
        fontSize: 13,
        fontWeight: '700',
        marginBottom: 15,
        textTransform: 'uppercase',
        letterSpacing: 1.2,
    },
    row: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 12,
    },
    iconContainer: {
        width: 40,
        height: 40,
        borderRadius: 12,
        alignItems: 'center',
        justifyContent: 'center',
        marginRight: 15,
        borderCurve: 'continuous',
    },
    rowContent: {
        flex: 1,
    },
    label: {
        fontSize: 16,
        fontWeight: '600',
    },
    value: {
        fontSize: 14,
        marginTop: 2,
    },
    valueSub: {
        fontSize: 12,
        color: '#A0AEC0',
        marginTop: 2,
    },
    separator: {
        height: 1,
        marginVertical: 5,
        marginLeft: 55,
    },
    logoutButton: {
        marginTop: 15,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
        backgroundColor: '#991B1B',
        borderRadius: 16,
        borderCurve: 'continuous',
    },
    logoutButtonText: {
        color: '#FFFFFF',
        fontSize: 16,
        fontWeight: '700',
    },
    testButton: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 14,
        borderRadius: 14,
        borderCurve: 'continuous',
        marginBottom: 12,
    },
    testButtonText: {
        color: '#FFF',
        fontSize: 15,
        fontWeight: '700',
    },
    statusBox: {
        flexDirection: 'row',
        alignItems: 'flex-start',
        padding: 12,
        borderRadius: 12,
        borderCurve: 'continuous',
    },
    statusText: {
        fontSize: 13,
        fontWeight: '500',
        flex: 1,
    },
});
