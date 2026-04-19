import React, { useState, useEffect } from 'react';
import { StyleSheet, Text, View, TouchableOpacity, ScrollView, Dimensions, Alert } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { useNavigation } from '@react-navigation/native';
import { Audio } from 'expo-av';
import { useRecordings, RecordingEntry } from '../context/RecordingsContext';


const { width } = Dimensions.get('window');

export default function RecordingsScreen() {
    const { colors, isDarkMode } = useTheme();
    const navigation = useNavigation<any>();
    const { recordings, deleteRecording, clearAll } = useRecordings();
    
    const [sound, setSound] = useState<Audio.Sound | null>(null);
    const [playingId, setPlayingId] = useState<string | null>(null);

    useEffect(() => {
        return sound ? () => { sound.unloadAsync(); } : undefined;
    }, [sound]);

    const playRecording = async (entry: RecordingEntry) => {
        try {
            if (sound) {
                await sound.unloadAsync();
            }
            
            if (playingId === entry.id) {
                setPlayingId(null);
                return;
            }

            const { sound: newSound } = await Audio.Sound.createAsync(
                { uri: entry.uri },
                { shouldPlay: true }
            );
            
            setSound(newSound);
            setPlayingId(entry.id);
            
            newSound.setOnPlaybackStatusUpdate((status) => {
                if (status.isLoaded && !status.isPlaying && status.didJustFinish) {
                    setPlayingId(null);
                }
            });
        } catch (error) {
            console.error('Failed to play recording', error);
            Alert.alert('Error', 'Could not play this recording.');
        }
    };

    const handleDelete = (id: string) => {
        Alert.alert(
            'Delete Recording',
            'Are you sure you want to remove this recording from your history?',
            [
                { text: 'Cancel', style: 'cancel' },
                { text: 'Delete', style: 'destructive', onPress: () => deleteRecording(id) }
            ]
        );
    };

    const formatDate = (timestamp: number) => {
        const date = new Date(timestamp);
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    };

    return (
        <View style={{ flex: 1, backgroundColor: colors.background }}>
            <StatusBar style={isDarkMode ? 'light' : 'dark'} />
            
            {/* Header */}
            <View style={[styles.header, { borderBottomColor: isDarkMode ? '#2D3748' : '#EDF2F7' }]}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
                    <Ionicons name="chevron-back" size={28} color={colors.text} />
                </TouchableOpacity>
                <Text style={[styles.headerTitle, { color: colors.text }]}>Recordings Library</Text>
                {recordings.length > 0 ? (
                    <TouchableOpacity onPress={clearAll}>
                        <Text style={[styles.clearText, { color: '#E53E3E' }]}>Clear All</Text>
                    </TouchableOpacity>
                ) : <View style={{ width: 40 }} />}
            </View>

            <ScrollView contentContainerStyle={styles.scrollContainer}>
                {recordings.length === 0 ? (
                    <View style={styles.emptyState}>
                        <View style={[styles.emptyIconContainer, { backgroundColor: isDarkMode ? '#2D3748' : '#F7FAFC' }]}>
                            <Ionicons name="mic-off" size={64} color="#A0AEC0" />
                        </View>
                        <Text style={[styles.emptyTitle, { color: colors.text }]}>No Recordings Yet</Text>
                        <Text style={styles.emptySub}>Capture audio from the Dashboard to see your history here.</Text>
                        <TouchableOpacity 
                            style={[styles.goBackButton, { backgroundColor: colors.primary }]}
                            onPress={() => navigation.navigate('Dashboard')}
                        >
                            <Text style={styles.goBackText}>Go to Dashboard</Text>
                        </TouchableOpacity>
                    </View>
                ) : (
                    recordings.map((recording) => (
                        <View 
                            key={recording.id} 
                            style={[styles.recordingCard, { backgroundColor: colors.card }]}
                        >
                            <View style={styles.cardLeft}>
                                <View style={[styles.iconContainer, { backgroundColor: isDarkMode ? '#2D3748' : '#EBF8FF' }]}>
                                    <Ionicons name="musical-note" size={24} color={colors.primary} />
                                </View>
                                <View style={styles.metaContainer}>
                                    <Text style={[styles.categoryText, { color: colors.text }]}>{recording.categoryLabel}</Text>
                                    <Text style={styles.dateText}>{formatDate(recording.createdAt)}</Text>
                                </View>
                            </View>
                            
                            <View style={styles.cardRight}>
                                <TouchableOpacity 
                                    style={[styles.actionButton, { backgroundColor: playingId === recording.id ? '#E53E3E' : colors.primary }]}
                                    onPress={() => playRecording(recording)}
                                >
                                    <Ionicons name={playingId === recording.id ? "stop" : "play"} size={20} color="#FFF" />
                                </TouchableOpacity>
                                <TouchableOpacity 
                                    style={[styles.deleteButton, { backgroundColor: isDarkMode ? '#2D3748' : '#FFF5F5' }]}
                                    onPress={() => handleDelete(recording.id)}
                                >
                                    <Ionicons name="trash-outline" size={20} color="#E53E3E" />
                                </TouchableOpacity>
                            </View>
                        </View>
                    ))
                )}
            </ScrollView>
        </View>
    );
}

const styles = StyleSheet.create({
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingTop: 60,
        paddingBottom: 20,
        paddingHorizontal: 20,
        borderBottomWidth: 1,
    },
    backButton: {
        padding: 4,
    },
    headerTitle: {
        fontSize: 20,
        fontWeight: 'bold',
    },
    clearText: {
        fontSize: 14,
        fontWeight: '600',
    },
    scrollContainer: {
        padding: 20,
        paddingBottom: 100,
    },
    emptyState: {
        marginTop: 100,
        alignItems: 'center',
        justifyContent: 'center',
    },
    emptyIconContainer: {
        width: 120,
        height: 120,
        borderRadius: 60,
        alignItems: 'center',
        justifyContent: 'center',
        marginBottom: 24,
    },
    emptyTitle: {
        fontSize: 22,
        fontWeight: 'bold',
        marginBottom: 10,
    },
    emptySub: {
        fontSize: 16,
        color: '#718096',
        textAlign: 'center',
        paddingHorizontal: 40,
        marginBottom: 30,
    },
    goBackButton: {
        paddingHorizontal: 24,
        paddingVertical: 12,
        borderRadius: 12,
    },
    goBackText: {
        color: '#FFF',
        fontWeight: 'bold',
        fontSize: 16,
    },
    recordingCard: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: 16,
        borderRadius: 20,
        marginBottom: 16,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.05,
        shadowRadius: 10,
        elevation: 2,
    },
    cardLeft: {
        flexDirection: 'row',
        alignItems: 'center',
        flex: 1,
    },
    iconContainer: {
        width: 50,
        height: 50,
        borderRadius: 25,
        alignItems: 'center',
        justifyContent: 'center',
        marginRight: 16,
    },
    metaContainer: {
        flex: 1,
    },
    categoryText: {
        fontSize: 16,
        fontWeight: '700',
        marginBottom: 4,
    },
    dateText: {
        fontSize: 12,
        color: '#A0AEC0',
    },
    cardRight: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    actionButton: {
        width: 44,
        height: 44,
        borderRadius: 22,
        alignItems: 'center',
        justifyContent: 'center',
        marginRight: 10,
    },
    deleteButton: {
        width: 44,
        height: 44,
        borderRadius: 22,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 1,
        borderColor: '#FED7D7',
    },
});
