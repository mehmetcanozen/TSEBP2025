import React from 'react';
import { StyleSheet, Text, View, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { LinearGradient } from 'expo-linear-gradient';

export default function NotificationsScreen() {
    const { colors, isDarkMode } = useTheme();

    const notifications = [
        { id: 1, title: 'Welcome to Suppression App', desc: 'Thank you for using our application. Start your first validation now!', time: '2 hours ago', icon: 'sparkles' },
        { id: 2, title: 'Profile Updated', desc: 'Your profile changes have been successfully saved.', time: '1 day ago', icon: 'person-circle' },
    ];

    return (
        <ScrollView contentContainerStyle={[styles.container, { backgroundColor: colors.background }]} bounces={false}>
            <View style={styles.headerWrapper}>
                <LinearGradient
                    colors={[colors.headerGradientStart || '#FF8A00', colors.headerGradientEnd || '#FF5722']}
                    start={{ x: 0, y: 0 }}
                    end={{ x: 1, y: 1 }}
                    style={styles.headerBackground}
                />
                
                <View style={[styles.headerTopBar, {marginTop: 10}]}>
                    <Text style={styles.headerTopText}>App Alerts</Text>
                    <Ionicons name="notifications-outline" size={20} color="#FFF" />
                </View>

                <View style={styles.headerGreeting}>
                    <Text style={styles.greetingTitle}>Notifications</Text>
                    <Text style={styles.greetingSubtitle}>Your recent activities and alerts</Text>
                </View>
            </View>

            <View style={styles.contentWrapper}>
                {notifications.map(notif => (
                    <View key={notif.id} style={[styles.card, { backgroundColor: colors.card }]}>
                        <View style={[styles.iconContainer, { backgroundColor: isDarkMode ? '#4A5568' : '#FFF0E5' }]}>
                            <Ionicons name={notif.icon as any} size={20} color={colors.primary} />
                        </View>
                        <View style={styles.cardContent}>
                            <Text style={[styles.title, { color: colors.text }]}>{notif.title}</Text>
                            <Text style={[styles.desc, { color: colors.textSecondary }]}>{notif.desc}</Text>
                            <Text style={styles.time}>{notif.time}</Text>
                        </View>
                    </View>
                ))}
            </View>
        </ScrollView>
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
        flexDirection: 'row',
        alignItems: 'center',
        borderRadius: 24,
        padding: 20,
        marginBottom: 15,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 10 },
        shadowOpacity: 0.05,
        shadowRadius: 15,
        elevation: 8,
        borderCurve: 'continuous',
    },
    iconContainer: {
        width: 44,
        height: 44,
        borderRadius: 14,
        alignItems: 'center',
        justifyContent: 'center',
        marginRight: 15,
        borderCurve: 'continuous',
    },
    cardContent: {
        flex: 1,
    },
    title: {
        fontSize: 15,
        fontWeight: '700',
        marginBottom: 3,
    },
    desc: {
        fontSize: 13,
        lineHeight: 18,
        marginBottom: 6,
    },
    time: {
        fontSize: 11,
        color: '#A0AEC0',
        fontWeight: '500',
    }
});
