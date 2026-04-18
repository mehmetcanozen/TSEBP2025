import React, { useState } from 'react';
import { StyleSheet, Text, View, TouchableOpacity, ScrollView, Dimensions, Image } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { useSuppressionDemo } from '../hooks/useSuppressionDemo';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { LinearGradient } from 'expo-linear-gradient';
import { useAuth } from '../context/AuthContext';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import AsyncStorage from '@react-native-async-storage/async-storage';

const { width } = Dimensions.get('window');

export default function DashboardScreen() {
    const { userInfo, userToken } = useAuth();
    const {
        startLive,
        stopLive,
        status,
        isLive,
        target,
        setTarget,
        debugInfo,
        runtimeInfo,
        liveStatus,
        meter,
        availableTargets,
    } = useSuppressionDemo({ accessToken: userToken });

    const { colors, isDarkMode } = useTheme();
    const navigation = useNavigation<any>();

    const [notificationsEnabled, setNotificationsEnabled] = useState(true);

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
                
                {/* Top Bar */}
                <View style={[styles.headerTopBar, {marginTop: 10, justifyContent: 'flex-end'}]}>
                    <View style={styles.headerTopRight}>
                        <TouchableOpacity onPress={toggleNotifications} activeOpacity={0.8} style={{ padding: 5, marginRight: 10 }}>
                            <Ionicons name={notificationsEnabled ? "notifications" : "notifications-off-outline"} size={22} color="#FFF" />
                        </TouchableOpacity>
                        <TouchableOpacity 
                            style={{ flexDirection: 'row', alignItems: 'center' }} 
                            onPress={() => navigation.navigate('Profile')} 
                            activeOpacity={0.8}
                        >
                            <Text style={{ color: '#FFF', fontWeight: 'bold', marginRight: 10, fontSize: 15 }}>
                                {userInfo?.full_name?.split(' ')[0] || userInfo?.username || 'User'}
                            </Text>
                            <View style={styles.avatarPlaceholder}>
                                {userInfo?.photo_uri ? (
                                    <Image source={{ uri: userInfo.photo_uri }} style={{ width: '100%', height: '100%', borderRadius: 16 }} />
                                ) : (
                                    <Ionicons name="person" size={20} color={colors.primary} />
                                )}
                            </View>
                        </TouchableOpacity>
                    </View>
                </View>

                {/* Greeting */}
                <View style={styles.headerGreeting}>
                    <Text style={styles.greetingTitle}>Hi {userInfo?.full_name || userInfo?.username || 'Developer'},</Text>
                    <Text style={styles.greetingSubtitle}>AI Powered Noise Cancellation</Text>
                </View>
            </View>

            <View style={styles.contentWrapper}>
                {/* Main Overlapping Card */}
                <View style={[styles.mainCard, { backgroundColor: colors.card }]}>
                    <View style={styles.mainCardTop}>
                        <View style={styles.mainCardTopLeft}>
                            <View style={[styles.iconContainerBlue, { backgroundColor: isDarkMode ? '#4A5568' : '#EBF8FF' }]}>
                                <Ionicons name="pulse" size={16} color={colors.primary} />
                            </View>
                            {/* Status text removed */}
                        </View>
                        <TouchableOpacity
                            style={[styles.topUpButton, { backgroundColor: colors.primary }, isLive && { backgroundColor: '#E53E3E' }]}
                            onPress={isLive ? stopLive : startLive}
                            activeOpacity={0.8}
                        >
                            <Text style={styles.topUpButtonText}>{isLive ? "Stop Live" : "Start Live"}</Text>
                        </TouchableOpacity>
                    </View>

                    <View style={[styles.divider, { backgroundColor: isDarkMode ? '#4A5568' : '#EDF2F7' }]} />

                    <View style={styles.mainCardBottom}>
                        <View style={styles.mainCardBottomLeft}>
                            <View style={styles.tagsRow}>
                                <View style={[styles.tag, { backgroundColor: isDarkMode ? '#22543D' : '#E6FFFA' }]}>
                                    <Text style={[styles.tagText, { color: isDarkMode ? '#9AE6B4' : '#319795' }]}>AI Mode</Text>
                                </View>
                                <View style={[styles.tag, { backgroundColor: isDarkMode ? '#2C5282' : '#EBF8FF' }]}>
                                    <Text style={[styles.tagText, { color: isDarkMode ? '#90CDF4' : '#3182CE' }]}>Denoise</Text>
                                </View>
                            </View>

                            <View style={styles.targetInfoRow}>
                                <View style={[styles.iconContainerGreen, { backgroundColor: isDarkMode ? '#22543D' : '#C6F6D5' }]}>
                                    <Ionicons name="swap-vertical" size={16} color={isDarkMode ? '#9AE6B4' : '#38A169'} />
                                </View>
                                <View style={{ marginLeft: 10 }}>
                                    <Text style={[styles.activeTargetTitle, { color: colors.text }]}>
                                        {availableTargets.find(t => t.id === target)?.label}
                                    </Text>
                                    <Text style={styles.activeTargetSubtitle}>
                                        {isLive ? 'Edge suppression active' : 'Ready for live suppression'}
                                    </Text>
                                </View>
                            </View>
                        </View>

                        <View style={styles.mainCardBottomRight}>
                            <View style={styles.circularProgressWrap}>
                                <View style={[styles.circularProgressInner, { backgroundColor: colors.card }]}>
                                    <Text style={[styles.circleValueText, { color: colors.text }]}>{isLive ? "LIVE" : "RDY"}</Text>
                                    <Text style={styles.circleSubText}>/ SNS</Text>
                                </View>
                                <View style={[styles.circleBorder, { borderRightColor: colors.primary, borderBottomColor: colors.primary, transform: [{ rotate: isLive ? '45deg' : '225deg' }] }]} />
                                <View style={[styles.circleBorderTrack, { borderColor: isDarkMode ? '#4A5568' : '#EDF2F7' }]} />
                            </View>
                        </View>
                    </View>
                </View>

                {/* Select Noise Type Section */}
                    <Text style={[styles.sectionTitle, { color: colors.text }]}>Select Noise To Suppress</Text>

                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.horizontalScroll}>
                    {availableTargets.map((t) => (
                        <TouchableOpacity
                            key={t.id}
                            style={[
                                styles.horizontalCard,
                                { backgroundColor: colors.card },
                                target === t.id && { borderColor: colors.primary, borderWidth: 2 }
                            ]}
                            onPress={() => setTarget(t.id)}
                            activeOpacity={0.8}
                        >
                            <View style={styles.horizontalCardTop}>
                                <View style={[
                                    styles.iconContainerGreen, 
                                    { backgroundColor: isDarkMode ? '#4A5568' : '#C6F6D5' },
                                    target === t.id && { backgroundColor: colors.primary }
                                ]}>
                                    <Ionicons name={t.icon as any} size={16} color={target === t.id ? '#FFF' : (isDarkMode ? '#9AE6B4' : '#38A169')} />
                                </View>
                                <Text style={[styles.horizontalCardTitle, { color: colors.text }]} numberOfLines={1}>{t.label}</Text>
                            </View>
                            <Text style={[styles.horizontalCardDesc, { color: isDarkMode ? '#E2E8F0' : '#4A5568' }]}>Apply target</Text>
                            <Text style={styles.horizontalCardSub}>{t.transient ? 'Transient-aware profile' : 'Steady-noise profile'}</Text>
                            {/* Option and chevron removed */}
                        </TouchableOpacity>
                    ))}
                </ScrollView>

                {/* Runtime Section */}
                {(runtimeInfo || debugInfo) && (
                    <View style={styles.playbackSection}>
                        <Text style={[styles.sectionTitle, { color: colors.text, marginBottom: 15 }]}>Live Runtime</Text>

                        <View style={[styles.playbackCard, { backgroundColor: colors.card }]}>
                            <View style={styles.playbackLeft}>
                                <View style={[styles.iconContainerGreen, { backgroundColor: isDarkMode ? '#22543D' : '#C6F6D5' }]}>
                                    <Ionicons name="hardware-chip-outline" size={16} color={isDarkMode ? '#9AE6B4' : '#38A169'} />
                                </View>
                                <View style={{ marginLeft: 15 }}>
                                    <Text style={[styles.playbackTitle, { color: colors.text }]}>Runtime</Text>
                                    <Text style={styles.playbackSub}>
                                        {runtimeInfo?.displayName ?? runtimeInfo?.provider ?? 'pending'} / {runtimeInfo?.modelVersion ?? 'unloaded'}
                                    </Text>
                                </View>
                            </View>
                            <View style={[styles.playBadge, { backgroundColor: isDarkMode ? '#4A5568' : '#FFF0E5' }]}>
                                <Text style={[styles.playBadgeText, { color: colors.primary }]}>
                                    {runtimeInfo?.sampleRate ?? '--'} Hz
                                </Text>
                            </View>
                        </View>

                        <View style={[styles.playbackCard, { backgroundColor: colors.card }]}>
                            <View style={styles.playbackLeft}>
                                <View style={[styles.iconContainerGreen, { backgroundColor: isDarkMode ? '#2C5282' : '#EBF8FF' }]}>
                                    <Ionicons name="speedometer-outline" size={16} color={isDarkMode ? '#90CDF4' : '#3182CE'} />
                                </View>
                                <View style={{ marginLeft: 15 }}>
                                    <Text style={[styles.playbackTitle, { color: colors.text }]}>Live Metrics</Text>
                                    <Text style={styles.playbackSub}>
                                        {liveStatus?.inferenceMs?.toFixed(1) ?? '--'} ms infer / {liveStatus?.queueDepthMs?.toFixed(1) ?? '--'} ms queue
                                    </Text>
                                </View>
                            </View>
                            <View style={[styles.playBadge, { backgroundColor: colors.primary }]}>
                                <Text style={[styles.playBadgeText, { color: '#FFF' }]}>
                                    XR {liveStatus?.xruns ?? 0}
                                </Text>
                            </View>
                        </View>

                        <View style={[styles.playbackCard, { backgroundColor: colors.card, alignItems: 'flex-start' }]}>
                            <View style={{ flex: 1 }}>
                                <Text style={[styles.playbackTitle, { color: colors.text, marginBottom: 6 }]}>Status</Text>
                                <Text style={styles.playbackSub}>{status}</Text>
                                <Text style={[styles.debugText, { color: colors.text, marginTop: 12 }]}>
                                    {debugInfo}
                                </Text>
                                {meter && (
                                    <Text style={styles.playbackSub}>
                                        In peak {meter.peakIn.toFixed(3)} / Out peak {meter.peakOut.toFixed(3)}
                                    </Text>
                                )}
                            </View>
                        </View>
                    </View>
                )}
            </View>

            <StatusBar style="light" />
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
        marginBottom: 30,
    },
    headerTopText: {
        color: 'rgba(255,255,255,0.8)',
        fontSize: 12,
        fontWeight: '600',
    },
    headerTopRight: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    avatarPlaceholder: {
        width: 32,
        height: 32,
        borderRadius: 16,
        backgroundColor: '#FFF',
        justifyContent: 'center',
        alignItems: 'center',
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
    mainCard: {
        borderRadius: 24,
        padding: 20,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 10 },
        shadowOpacity: 0.05,
        shadowRadius: 15,
        elevation: 8,
        marginBottom: 25,
        borderCurve: 'continuous',
    },
    mainCardTop: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingBottom: 15,
    },
    mainCardTopLeft: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    iconContainerBlue: {
        width: 36,
        height: 36,
        borderRadius: 10,
        justifyContent: 'center',
        alignItems: 'center',
        borderCurve: 'continuous',
    },
    statusLabelText: {
        fontSize: 12,
        color: '#A0AEC0',
    },
    statusValueText: {
        fontSize: 14,
        fontWeight: 'bold',
    },
    topUpButton: {
        paddingHorizontal: 16,
        paddingVertical: 10,
        borderRadius: 20,
        borderCurve: 'continuous',
    },
    topUpButtonText: {
        color: '#FFF',
        fontSize: 13,
        fontWeight: '600',
    },
    divider: {
        height: 1,
        marginHorizontal: -20,
        marginBottom: 15,
    },
    mainCardBottom: {
        flexDirection: 'row',
        justifyContent: 'space-between',
    },
    mainCardBottomLeft: {
        flex: 1,
    },
    tagsRow: {
        flexDirection: 'row',
        marginBottom: 15,
    },
    tag: {
        paddingHorizontal: 10,
        paddingVertical: 4,
        borderRadius: 8,
        marginRight: 8,
        borderCurve: 'continuous',
    },
    tagText: {
        fontSize: 10,
        fontWeight: '600',
    },
    targetInfoRow: {
        flexDirection: 'row',
        alignItems: 'center',
        marginBottom: 10,
    },
    iconContainerGreen: {
        width: 32,
        height: 32,
        borderRadius: 16,
        justifyContent: 'center',
        alignItems: 'center',
    },
    activeTargetTitle: {
        fontSize: 14,
        fontWeight: 'bold',
    },
    activeTargetSubtitle: {
        fontSize: 12,
        color: '#A0AEC0',
    },
    activeUntilText: {
        fontSize: 11,
        color: '#A0AEC0',
        marginTop: 5,
    },
    mainCardBottomRight: {
        justifyContent: 'center',
        alignItems: 'center',
        width: 80,
    },
    circularProgressWrap: {
        width: 76,
        height: 76,
        justifyContent: 'center',
        alignItems: 'center',
    },
    circularProgressInner: {
        width: 60,
        height: 60,
        borderRadius: 30,
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 2,
    },
    circleBorder: {
        position: 'absolute',
        top: 0, left: 0, right: 0, bottom: 0,
        borderWidth: 6,
        borderRadius: 38,
        borderTopColor: 'transparent',
        borderLeftColor: 'transparent',
        zIndex: 1,
    },
    circleBorderTrack: {
        position: 'absolute',
        top: 0, left: 0, right: 0, bottom: 0,
        borderWidth: 6,
        borderRadius: 38,
        zIndex: 0,
    },
    circleValueText: {
        fontSize: 16,
        fontWeight: 'bold',
    },
    circleSubText: {
        fontSize: 10,
        color: '#A0AEC0',
    },
    sectionHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 15,
        paddingHorizontal: 4,
    },
    sectionTitle: {
        fontSize: 18,
        fontWeight: '700',
    },
    sectionLink: {
        fontSize: 14,
        fontWeight: '600',
    },
    horizontalScroll: {
        paddingRight: 20,
        paddingBottom: 10,
    },
    horizontalCard: {
        width: 140,
        borderRadius: 20,
        padding: 16,
        marginRight: 15,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.03,
        shadowRadius: 8,
        elevation: 3,
        borderWidth: 2,
        borderColor: 'transparent',
        borderCurve: 'continuous',
    },
    horizontalCardTop: {
        flexDirection: 'row',
        alignItems: 'center',
        marginBottom: 12,
    },
    horizontalCardTitle: {
        fontWeight: 'bold',
        fontSize: 14,
        marginLeft: 8,
        flex: 1,
    },
    horizontalCardDesc: {
        fontSize: 12,
        fontWeight: '600',
        marginBottom: 4,
    },
    horizontalCardSub: {
        fontSize: 11,
        color: '#A0AEC0',
        marginBottom: 15,
    },
    cardPriceRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
    },
    cardPrice: {
        fontSize: 16,
        fontWeight: 'bold',
    },
    playbackSection: {
        marginTop: 15,
    },
    playbackCard: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: 16,
        borderRadius: 20,
        marginBottom: 12,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.03,
        shadowRadius: 8,
        elevation: 3,
        borderCurve: 'continuous',
    },
    playbackLeft: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    playbackTitle: {
        fontSize: 14,
        fontWeight: 'bold',
        marginBottom: 2,
    },
    playbackSub: {
        fontSize: 12,
        color: '#A0AEC0',
    },
    playBadge: {
        paddingHorizontal: 14,
        paddingVertical: 6,
        borderRadius: 16,
        borderCurve: 'continuous',
    },
    playBadgeText: {
        fontSize: 12,
        fontWeight: 'bold',
    },
    path: {
        fontSize: 11,
        textAlign: 'center',
        marginTop: 5,
    },
    debugText: {
        fontSize: 12,
        marginBottom: 10,
        fontFamily: 'monospace',
    },
});
