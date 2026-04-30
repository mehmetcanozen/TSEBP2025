import React, { useState } from 'react';
import {
    StyleSheet, Text, View, TouchableOpacity,
    ScrollView, Dimensions, Image, Switch,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { useSuppressionDemo } from '../hooks/useSuppressionDemo';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { LinearGradient } from 'expo-linear-gradient';
import { useAuth } from '../context/AuthContext';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Audio } from 'expo-av';

const { width } = Dimensions.get('window');

export default function DashboardScreen() {
    // ── Auth & Engine ────────────────────────────────────────────
    const { userInfo, userToken } = useAuth();
    const {
        startLive, stopLive,
        status, phase, isLive,
        target, setTarget,
        debugInfo, runtimeInfo, liveStatus, meter,
        availableTargets,
        isRecordEnabled, setIsRecordEnabled,
        lastRecordingUri, lastRecordingFileName, lastRecordingFilePath,
        lastRecordingFileSizeBytes, clearLastRecording,
    } = useSuppressionDemo({ accessToken: userToken });

    const { colors, isDarkMode } = useTheme();
    const navigation = useNavigation<any>();

    // ── Local state ──────────────────────────────────────────────
    const [notificationsEnabled, setNotificationsEnabled] = useState(true);
    const [sound, setSound] = useState<Audio.Sound | null>(null);
    const [isPlaying, setIsPlaying] = useState(false);
    const [filterStrength, setFilterStrength] = useState(100); // visual only
    const [showRuntime, setShowRuntime] = useState(false);
    const [showTargets, setShowTargets] = useState(false);

    // ── Load notification preference ─────────────────────────────
    useFocusEffect(
        React.useCallback(() => {
            AsyncStorage.getItem('APP_NOTIFICATIONS').then(v => {
                if (v !== null) setNotificationsEnabled(v === 'true');
            }).catch(() => {});
        }, [])
    );

    const toggleNotifications = async () => {
        const next = !notificationsEnabled;
        setNotificationsEnabled(next);
        await AsyncStorage.setItem('APP_NOTIFICATIONS', String(next));
    };

    // ── Playback ─────────────────────────────────────────────────
    const playRecording = async () => {
        if (!lastRecordingUri) return;
        try {
            await Audio.setAudioModeAsync({
                allowsRecordingIOS: false,
                playsInSilentModeIOS: true,
                shouldDuckAndroid: true,
                staysActiveInBackground: false,
                playThroughEarpieceAndroid: false,
            });
            if (sound) await sound.unloadAsync();
            const { sound: s } = await Audio.Sound.createAsync(
                { uri: lastRecordingUri }, { shouldPlay: true }
            );
            setSound(s);
            setIsPlaying(true);
            s.setOnPlaybackStatusUpdate(st => {
                if (st.isLoaded && !st.isPlaying && st.didJustFinish) setIsPlaying(false);
            });
        } catch (e) { console.error('Playback error', e); }
    };

    const stopPlayback = async () => {
        if (sound) { await sound.stopAsync(); setIsPlaying(false); }
    };

    React.useEffect(() => {
        return sound ? () => { sound.unloadAsync(); } : undefined;
    }, [sound]);

    // ── Derived ──────────────────────────────────────────────────
    const selectedTarget = availableTargets.find(t => t.id === target);
    const liveButtonDisabled = phase === 'preparing' || phase === 'stopping';
    const liveButtonLabel = phase === 'preparing'
        ? 'Preparing audio...'
        : phase === 'stopping'
            ? 'Saving output...'
            : isLive
                ? 'Tap to stop'
                : 'Tap to start listening';
    const meterPct = meter
        ? Math.min(Math.round(Math.abs(meter.peakIn) * 300), 100)
        : 0;

    // ── Color aliases ────────────────────────────────────────────
    const bg      = colors.background;
    const card    = colors.card;
    const primary = colors.primary;
    const txt     = colors.text;
    const sub     = isDarkMode ? '#94A3B8' : '#64748B';
    const div     = isDarkMode ? '#334155' : '#E2E8F0';

    return (
        <View style={{ flex: 1, backgroundColor: bg }}>
            <StatusBar style="light" />

            {/* ── HEADER ── */}
            <LinearGradient
                colors={[colors.headerGradientStart || '#1E3A8A', colors.headerGradientEnd || '#8B5CF6']}
                start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
                style={styles.header}
            >
                <View style={styles.headerRow}>
                    <Text style={styles.headerTitle}>Live Listen</Text>
                    <View style={styles.headerIcons}>
                        <TouchableOpacity onPress={toggleNotifications} style={styles.iconBtn}>
                            <Ionicons
                                name={notificationsEnabled ? 'notifications' : 'notifications-off-outline'}
                                size={22} color="#FFF"
                            />
                        </TouchableOpacity>
                        <TouchableOpacity
                            style={styles.avatarBtn}
                            onPress={() => navigation.navigate('Profile')}
                            activeOpacity={0.8}
                        >
                            {userInfo?.photo_uri
                                ? <Image source={{ uri: userInfo.photo_uri }} style={styles.avatarImg} />
                                : (
                                    <View style={[styles.avatarFallback, { backgroundColor: '#FFF' }]}>
                                        <Ionicons name="person" size={16} color={primary} />
                                    </View>
                                )
                            }
                        </TouchableOpacity>
                    </View>
                </View>
                <Text style={styles.headerSub}>
                    {userInfo?.full_name?.split(' ')[0] || userInfo?.username || 'User'} •{' '}
                    {isLive ? 'Session active' : 'Ready to listen'}
                </Text>
            </LinearGradient>

            <ScrollView
                contentContainerStyle={[styles.scroll, { backgroundColor: bg }]}
                showsVerticalScrollIndicator={false}
            >
                {/* ── BIG LIVE BUTTON ── */}
                <View style={styles.liveSection}>
                    <TouchableOpacity
                        style={[
                            styles.liveRing,
                            {
                                borderColor: isLive ? '#EF4444' : primary,
                                opacity: liveButtonDisabled ? 0.55 : 1,
                            }
                        ]}
                        onPress={isLive ? stopLive : startLive}
                        disabled={liveButtonDisabled}
                        activeOpacity={0.85}
                    >
                        <View style={[styles.liveCore, { backgroundColor: isLive ? '#EF4444' : primary }]}>
                            <Ionicons name={isLive ? 'stop' : 'ear'} size={38} color="#FFF" />
                        </View>
                    </TouchableOpacity>
                    {isLive && (
                        <View style={styles.livePill}>
                            <View style={styles.liveDot} />
                            <Text style={styles.livePillText}>LIVE</Text>
                        </View>
                    )}
                    <Text style={[styles.liveCta, { color: sub }]}>
                        {liveButtonLabel}
                    </Text>
                </View>

                {/* ── SYSTEM SUGGESTIONS ── */}
                <View style={[styles.card, { backgroundColor: card }]}>
                    <Text style={[styles.cardLabel, { color: sub }]}>System Suggestions</Text>
                    <View style={styles.suggestionRow}>
                        <View style={[
                            styles.suggIcon,
                            { backgroundColor: isLive ? (isDarkMode ? '#1E3A5F' : '#DBEAFE') : (isDarkMode ? '#1E293B' : '#F1F5F9') }
                        ]}>
                            <Ionicons
                                name={isLive ? 'volume-high-outline' : 'ear-outline'}
                                size={18}
                                color={isLive ? (isDarkMode ? '#93C5FD' : '#2563EB') : sub}
                            />
                        </View>
                        <View style={{ flex: 1, marginLeft: 12 }}>
                            <Text style={[styles.suggText, { color: txt }]} numberOfLines={2}>
                                {isLive && status ? status : 'Start listening to see suggestions'}
                            </Text>
                            {isLive && (
                                <Text style={[styles.suggSub, { color: sub }]}>
                                    Tap to attenuate this sound
                                </Text>
                            )}
                        </View>
                    </View>
                </View>

                {/* ── TARGET SOUNDS (collapsible) ── */}
                <View style={[styles.card, { backgroundColor: card }]}>
                    <TouchableOpacity
                        style={styles.runtimeToggleRow}
                        onPress={() => setShowTargets(v => !v)}
                        activeOpacity={0.7}
                    >
                        <View>
                            <Text style={[styles.cardLabel, { color: sub, marginBottom: 2 }]}>Target Sounds</Text>
                            <Text style={[styles.recogTitle, { color: txt, fontSize: 14 }]}>
                                {selectedTarget?.label ?? 'None selected'}
                            </Text>
                        </View>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                            <View style={[styles.targetDot, { backgroundColor: primary }]}>
                                <Ionicons name={selectedTarget?.icon as any ?? 'musical-note'} size={13} color="#FFF" />
                            </View>
                            <Ionicons name={showTargets ? 'chevron-up' : 'chevron-down'} size={16} color={sub} />
                        </View>
                    </TouchableOpacity>

                    {showTargets && availableTargets.map((t, idx) => (
                        <TouchableOpacity
                            key={t.id}
                            style={[
                                styles.targetRow,
                                { borderTopColor: div, borderTopWidth: idx === 0 ? StyleSheet.hairlineWidth : StyleSheet.hairlineWidth }
                            ]}
                            onPress={() => setTarget(t.id)}
                            activeOpacity={0.7}
                        >
                            <View style={[
                                styles.targetDot,
                                { backgroundColor: target === t.id ? primary : (isDarkMode ? '#334155' : '#E2E8F0') }
                            ]}>
                                <Ionicons name={t.icon as any} size={13} color={target === t.id ? '#FFF' : sub} />
                            </View>
                            <Text style={[
                                styles.targetName,
                                { color: target === t.id ? primary : txt, fontWeight: target === t.id ? '700' : '500' }
                            ]}>
                                {t.label}
                            </Text>
                            <Text style={[styles.targetTag, { color: sub, backgroundColor: isDarkMode ? '#1E293B' : '#F1F5F9' }]}>
                                {t.transient ? 'Transient' : 'Steady'}
                            </Text>
                            {target === t.id
                                ? <Ionicons name="checkmark-circle" size={20} color={primary} />
                                : <View style={[styles.targetCircle, { borderColor: div }]} />
                            }
                        </TouchableOpacity>
                    ))}
                </View>


                {/* ── FILTER STRENGTH ── */}
                <View style={[styles.card, { backgroundColor: card }]}>
                    <View style={styles.filterHeader}>
                        <Text style={[styles.cardLabel, { color: sub, marginBottom: 0 }]}>Filter Strength</Text>
                        <Text style={[styles.filterPct, { color: primary }]}>{filterStrength}%</Text>
                    </View>
                    <View style={[styles.filterTrack, { backgroundColor: isDarkMode ? '#1E293B' : '#F1F5F9' }]}>
                        <View style={[styles.filterFill, { width: `${filterStrength}%`, backgroundColor: primary }]} />
                    </View>
                    <View style={styles.filterBtns}>
                        <TouchableOpacity
                            style={[styles.filterBtn, { borderColor: div }]}
                            onPress={() => setFilterStrength(f => Math.max(0, f - 10))}
                        >
                            <Ionicons name="remove" size={20} color={txt} />
                        </TouchableOpacity>
                        <Text style={[styles.filterBtnLabel, { color: sub }]}>Adjust strength</Text>
                        <TouchableOpacity
                            style={[styles.filterBtn, { borderColor: div }]}
                            onPress={() => setFilterStrength(f => Math.min(100, f + 10))}
                        >
                            <Ionicons name="add" size={20} color={txt} />
                        </TouchableOpacity>
                    </View>
                </View>

                {/* ── SOUND RECOGNITION ── */}
                <View style={[styles.card, { backgroundColor: card }]}>
                    <View style={styles.recogRow}>
                        <View style={{ flex: 1 }}>
                            <Text style={[styles.cardLabel, { color: sub, marginBottom: 2 }]}>Sound Recognition</Text>
                            <Text style={[styles.recogTitle, { color: txt }]}>
                                {selectedTarget?.label ?? 'No target selected'}
                            </Text>
                        </View>
                        <Switch
                            value={isRecordEnabled}
                            onValueChange={setIsRecordEnabled}
                            trackColor={{ false: div, true: primary }}
                            thumbColor="#FFF"
                        />
                    </View>
                    {meter && isLive && (
                        <View style={{ marginTop: 14 }}>
                            <View style={styles.meterRow}>
                                <Text style={[styles.meterLabel, { color: sub }]}>Input Level</Text>
                                <Text style={[styles.meterPct, { color: primary }]}>{meterPct}%</Text>
                            </View>
                            <View style={[styles.meterTrack, { backgroundColor: isDarkMode ? '#1E293B' : '#F1F5F9' }]}>
                                <View style={[
                                    styles.meterFill,
                                    { width: `${meterPct}%`, backgroundColor: meterPct > 70 ? '#EF4444' : primary }
                                ]} />
                            </View>
                            <Text style={[styles.meterSub, { color: sub }]}>
                                In {meter.peakIn.toFixed(3)} / Out {meter.peakOut.toFixed(3)}
                            </Text>
                        </View>
                    )}
                    <Text style={[styles.recogHint, { color: sub }]}>
                        Identifies sounds in your environment using on-device analysis.
                    </Text>
                </View>

                {/* ── LATEST RESULT ── */}
                {lastRecordingUri && (
                    <View style={[styles.card, { backgroundColor: card }]}>
                        <View style={styles.latestHeader}>
                            <Text style={[styles.cardLabel, { color: sub, marginBottom: 0 }]}>Latest Result</Text>
                            <TouchableOpacity onPress={clearLastRecording}>
                                <Text style={{ color: '#EF4444', fontSize: 13, fontWeight: '600' }}>Clear</Text>
                            </TouchableOpacity>
                        </View>
                        <View style={styles.latestRow}>
                            <View style={[styles.latestIcon, { backgroundColor: isDarkMode ? '#1E293B' : '#EDE9FE' }]}>
                                <Ionicons name="musical-note" size={20} color={primary} />
                            </View>
                            <View style={{ flex: 1, marginLeft: 14 }}>
                                <Text style={[styles.latestTitle, { color: txt }]}>
                                    {lastRecordingFileName ?? 'Processed Snippet'}
                                </Text>
                                {/* Path display removed to clean up UI */}
                                {lastRecordingFileSizeBytes != null && (
                                    <Text style={[styles.latestMeta, { color: sub }]}>
                                        {(lastRecordingFileSizeBytes / 1024).toFixed(1)} KB
                                    </Text>
                                )}
                                <TouchableOpacity onPress={() => navigation.navigate('Recordings')}>
                                    <Text style={[styles.latestLink, { color: primary }]}>{'View in Library ->'}</Text>
                                </TouchableOpacity>
                            </View>
                            <TouchableOpacity
                                style={[styles.playBtn, { backgroundColor: primary }]}
                                onPress={isPlaying ? stopPlayback : playRecording}
                            >
                                <Ionicons name={isPlaying ? 'stop' : 'play'} size={18} color="#FFF" />
                            </TouchableOpacity>
                        </View>
                    </View>
                )}

                {/* ── RUNTIME (collapsible) ── */}
                {(runtimeInfo || debugInfo) && (
                    <View style={[styles.card, { backgroundColor: card }]}>
                        <TouchableOpacity
                            style={styles.runtimeToggleRow}
                            onPress={() => setShowRuntime(v => !v)}
                            activeOpacity={0.7}
                        >
                            <Text style={[styles.cardLabel, { color: sub, marginBottom: 0 }]}>Live Runtime</Text>
                            <Ionicons name={showRuntime ? 'chevron-up' : 'chevron-down'} size={16} color={sub} />
                        </TouchableOpacity>

                        {showRuntime && (
                            <View style={{ marginTop: 14 }}>
                                {[
                                    ['Provider', runtimeInfo?.displayName ?? runtimeInfo?.provider ?? '—'],
                                    ['Model', runtimeInfo?.modelVersion ?? '—'],
                                    ['Sample Rate', `${runtimeInfo?.sampleRate ?? '—'} Hz`],
                                    ['Inference', `${liveStatus?.inferenceMs?.toFixed(1) ?? '—'} ms`],
                                    ['Queue', `${liveStatus?.queueDepthMs?.toFixed(1) ?? '—'} ms`],
                                    ['XRuns', String(liveStatus?.xruns ?? 0)],
                                    ['AudioTrack Underruns', String(liveStatus?.audioTrackUnderruns ?? 0)],
                                    ['Limiter Hits', String(liveStatus?.limiterHits ?? 0)],
                                    ['Fail-open', String(liveStatus?.failOpenCount ?? 0)],
                                    ['Boundary Repairs', String(liveStatus?.boundaryRepairHits ?? 0)],
                                    ['Startup Blend', `${liveStatus?.startupBlendMs ?? 0} ms`],
                                    ['Post-filter', liveStatus?.waveformerPostFilter ?? 'off'],
                                    ['Raw Peak', meter?.rawOutPeak?.toFixed(3) ?? '--'],
                                    ['Final Peak', meter?.finalOutPeak?.toFixed(3) ?? meter?.peakOut?.toFixed(3) ?? '--'],
                                ].map(([k, v]) => (
                                    <View key={k} style={[styles.runtimeRow, { borderBottomColor: div }]}>
                                        <Text style={[styles.runtimeKey, { color: sub }]}>{k}</Text>
                                        <Text style={[styles.runtimeVal, { color: txt }]}>{v}</Text>
                                    </View>
                                ))}
                                {debugInfo && (
                                    <Text style={[styles.debugText, { color: sub }]}>{debugInfo}</Text>
                                )}
                            </View>
                        )}
                    </View>
                )}

                <View style={{ height: 36 }} />
            </ScrollView>
        </View>
    );
}

const styles = StyleSheet.create({
    // Header
    header: {
        paddingTop: 54,
        paddingBottom: 20,
        paddingHorizontal: 22,
    },
    headerRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 6,
    },
    headerTitle: {
        color: '#FFF',
        fontSize: 28,
        fontWeight: '800',
        letterSpacing: -0.5,
    },
    headerSub: {
        color: 'rgba(255,255,255,0.75)',
        fontSize: 13,
        fontWeight: '500',
    },
    headerIcons: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
    },
    iconBtn: {
        padding: 6,
    },
    avatarBtn: {},
    avatarImg: {
        width: 34,
        height: 34,
        borderRadius: 17,
    },
    avatarFallback: {
        width: 34,
        height: 34,
        borderRadius: 17,
        justifyContent: 'center',
        alignItems: 'center',
    },

    // Scroll
    scroll: {
        paddingTop: 28,
        paddingHorizontal: 16,
        paddingBottom: 20,
    },

    // Live button
    liveSection: {
        alignItems: 'center',
        marginBottom: 28,
    },
    liveRing: {
        width: 110,
        height: 110,
        borderRadius: 55,
        borderWidth: 3,
        justifyContent: 'center',
        alignItems: 'center',
        marginBottom: 12,
    },
    liveCore: {
        width: 90,
        height: 90,
        borderRadius: 45,
        justifyContent: 'center',
        alignItems: 'center',
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 6 },
        shadowOpacity: 0.2,
        shadowRadius: 12,
        elevation: 10,
    },
    livePill: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: '#EF4444',
        paddingHorizontal: 10,
        paddingVertical: 4,
        borderRadius: 20,
        marginBottom: 8,
        gap: 5,
    },
    liveDot: {
        width: 7,
        height: 7,
        borderRadius: 4,
        backgroundColor: '#FFF',
    },
    livePillText: {
        color: '#FFF',
        fontSize: 11,
        fontWeight: '800',
        letterSpacing: 1,
    },
    liveCta: {
        fontSize: 14,
        fontWeight: '500',
    },

    // Generic card
    card: {
        borderRadius: 18,
        padding: 18,
        marginBottom: 14,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.06,
        shadowRadius: 8,
        elevation: 3,
    },
    cardLabel: {
        fontSize: 12,
        fontWeight: '600',
        textTransform: 'uppercase',
        letterSpacing: 0.5,
        marginBottom: 14,
    },

    // Suggestions
    suggestionRow: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    suggIcon: {
        width: 38,
        height: 38,
        borderRadius: 11,
        justifyContent: 'center',
        alignItems: 'center',
    },
    suggText: {
        fontSize: 14,
        fontWeight: '600',
        lineHeight: 20,
    },
    suggSub: {
        fontSize: 12,
        marginTop: 2,
    },

    // Targets
    targetRow: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 13,
        gap: 10,
    },
    targetDot: {
        width: 30,
        height: 30,
        borderRadius: 15,
        justifyContent: 'center',
        alignItems: 'center',
    },
    targetName: {
        flex: 1,
        fontSize: 15,
    },
    targetTag: {
        fontSize: 11,
        fontWeight: '600',
        paddingHorizontal: 8,
        paddingVertical: 3,
        borderRadius: 8,
        overflow: 'hidden',
        marginRight: 4,
    },
    targetCircle: {
        width: 20,
        height: 20,
        borderRadius: 10,
        borderWidth: 1.5,
    },

    // Filter Strength
    filterHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 14,
    },
    filterPct: {
        fontSize: 26,
        fontWeight: '800',
    },
    filterTrack: {
        height: 6,
        borderRadius: 3,
        overflow: 'hidden',
        marginBottom: 14,
    },
    filterFill: {
        height: '100%',
        borderRadius: 3,
    },
    filterBtns: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
    },
    filterBtn: {
        width: 38,
        height: 38,
        borderRadius: 10,
        borderWidth: 1,
        justifyContent: 'center',
        alignItems: 'center',
    },
    filterBtnLabel: {
        fontSize: 13,
        fontWeight: '500',
    },

    // Sound Recognition
    recogRow: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    recogTitle: {
        fontSize: 16,
        fontWeight: '700',
    },
    meterRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        marginBottom: 6,
    },
    meterLabel: {
        fontSize: 12,
        fontWeight: '500',
    },
    meterPct: {
        fontSize: 12,
        fontWeight: '700',
    },
    meterTrack: {
        height: 5,
        borderRadius: 3,
        overflow: 'hidden',
    },
    meterFill: {
        height: '100%',
        borderRadius: 3,
    },
    meterSub: {
        fontSize: 11,
        marginTop: 5,
        fontFamily: 'monospace',
    },
    recogHint: {
        fontSize: 12,
        marginTop: 12,
        lineHeight: 17,
    },

    // Latest result
    latestHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 14,
    },
    latestRow: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    latestIcon: {
        width: 44,
        height: 44,
        borderRadius: 13,
        justifyContent: 'center',
        alignItems: 'center',
    },
    latestTitle: {
        fontSize: 14,
        fontWeight: '700',
        marginBottom: 3,
    },
    latestPath: {
        fontSize: 11,
        lineHeight: 15,
        marginBottom: 3,
    },
    latestMeta: {
        fontSize: 11,
        marginBottom: 3,
    },
    latestLink: {
        fontSize: 13,
        fontWeight: '600',
    },
    playBtn: {
        width: 42,
        height: 42,
        borderRadius: 21,
        justifyContent: 'center',
        alignItems: 'center',
    },

    // Runtime
    runtimeToggleRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
    },
    runtimeRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingVertical: 9,
        borderBottomWidth: StyleSheet.hairlineWidth,
    },
    runtimeKey: {
        fontSize: 13,
        fontWeight: '500',
    },
    runtimeVal: {
        fontSize: 13,
        fontWeight: '600',
    },
    debugText: {
        fontSize: 11,
        fontFamily: 'monospace',
        marginTop: 10,
        lineHeight: 17,
    },
});
