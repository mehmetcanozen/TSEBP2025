import React, { useState } from 'react';
import { StyleSheet, Text, View, TextInput, TouchableOpacity, KeyboardAvoidingView, Platform, Alert, ScrollView, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { LinearGradient } from 'expo-linear-gradient';
import { api } from '../services/api';

export default function ChangePasswordScreen({ navigation }: { navigation: any }) {
    const [oldPassword, setOldPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const [showOld, setShowOld] = useState(false);
    const [showNew, setShowNew] = useState(false);
    const [showConfirm, setShowConfirm] = useState(false);
    const { colors, isDarkMode } = useTheme();

    const handleChangePassword = async () => {
        if (!oldPassword || !newPassword || !confirmPassword) {
            Alert.alert('Error', 'Please fill in all fields.');
            return;
        }
        if (newPassword !== confirmPassword) {
            Alert.alert('Error', 'New passwords do not match.');
            return;
        }
        if (newPassword.length < 8) {
            Alert.alert('Error', 'New password must be at least 8 characters.');
            return;
        }

        setLoading(true);
        try {
            await api.put('/auth/change-password', {
                old_password: oldPassword,
                new_password: newPassword,
            });
            Alert.alert('Success', 'Password changed successfully!', [
                { text: 'OK', onPress: () => navigation.goBack() }
            ]);
        } catch (e: any) {
            const detail = e?.response?.data?.detail;
            const message = typeof detail === 'string' ? detail : e?.message || 'Failed to change password.';
            Alert.alert('Error', message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
            style={[styles.container, { backgroundColor: colors.background }]}
        >
            <ScrollView contentContainerStyle={styles.scrollContent} bounces={false} keyboardShouldPersistTaps="handled">
                {/* Header */}
                <View style={styles.headerWrapper}>
                    <LinearGradient
                        colors={[colors.headerGradientStart || '#FF8A00', colors.headerGradientEnd || '#FF5722']}
                        start={{ x: 0, y: 0 }}
                        end={{ x: 1, y: 1 }}
                        style={styles.headerBackground}
                    />
                    <TouchableOpacity style={styles.backButton} onPress={() => navigation.goBack()} activeOpacity={0.8}>
                        <Ionicons name="arrow-back" size={24} color="#FFF" />
                    </TouchableOpacity>
                    <View style={styles.headerGreeting}>
                        <Text style={styles.greetingTitle}>Change Password</Text>
                        <Text style={styles.greetingSubtitle}>Keep your account secure</Text>
                    </View>
                </View>

                {/* Form Card */}
                <View style={styles.contentWrapper}>
                    <View style={[styles.card, { backgroundColor: isDarkMode ? 'rgba(42,26,24,0.95)' : '#FFF' }]}>

                        {/* Current Password */}
                        <View style={styles.inputGroup}>
                            <Text style={[styles.label, { color: colors.text }]}>Current Password</Text>
                            <View style={[styles.inputRow, { backgroundColor: colors.inputBackground, borderColor: colors.border }]}>
                                <TextInput
                                    style={[styles.input, { color: colors.text }]}
                                    placeholder="Enter current password"
                                    placeholderTextColor={colors.textSecondary}
                                    value={oldPassword}
                                    onChangeText={setOldPassword}
                                    secureTextEntry={!showOld}
                                />
                                <TouchableOpacity onPress={() => setShowOld(!showOld)} style={styles.eyeButton}>
                                    <Ionicons name={showOld ? 'eye-off' : 'eye'} size={20} color={colors.textSecondary} />
                                </TouchableOpacity>
                            </View>
                        </View>

                        {/* New Password */}
                        <View style={styles.inputGroup}>
                            <Text style={[styles.label, { color: colors.text }]}>New Password</Text>
                            <View style={[styles.inputRow, { backgroundColor: colors.inputBackground, borderColor: colors.border }]}>
                                <TextInput
                                    style={[styles.input, { color: colors.text }]}
                                    placeholder="Enter new password (min 8 chars)"
                                    placeholderTextColor={colors.textSecondary}
                                    value={newPassword}
                                    onChangeText={setNewPassword}
                                    secureTextEntry={!showNew}
                                />
                                <TouchableOpacity onPress={() => setShowNew(!showNew)} style={styles.eyeButton}>
                                    <Ionicons name={showNew ? 'eye-off' : 'eye'} size={20} color={colors.textSecondary} />
                                </TouchableOpacity>
                            </View>
                        </View>

                        {/* Confirm New Password */}
                        <View style={styles.inputGroup}>
                            <Text style={[styles.label, { color: colors.text }]}>Confirm New Password</Text>
                            <View style={[styles.inputRow, { backgroundColor: colors.inputBackground, borderColor: colors.border }]}>
                                <TextInput
                                    style={[styles.input, { color: colors.text }]}
                                    placeholder="Re-enter new password"
                                    placeholderTextColor={colors.textSecondary}
                                    value={confirmPassword}
                                    onChangeText={setConfirmPassword}
                                    secureTextEntry={!showConfirm}
                                />
                                <TouchableOpacity onPress={() => setShowConfirm(!showConfirm)} style={styles.eyeButton}>
                                    <Ionicons name={showConfirm ? 'eye-off' : 'eye'} size={20} color={colors.textSecondary} />
                                </TouchableOpacity>
                            </View>
                        </View>

                        {/* Submit Button */}
                        <TouchableOpacity
                            style={[styles.button, { backgroundColor: colors.primary }, loading && { opacity: 0.7 }]}
                            onPress={handleChangePassword}
                            activeOpacity={0.8}
                            disabled={loading}
                        >
                            {loading ? (
                                <ActivityIndicator color="#FFF" />
                            ) : (
                                <>
                                    <Ionicons name="lock-closed" size={18} color="#FFF" style={{ marginRight: 8 }} />
                                    <Text style={styles.buttonText}>Update Password</Text>
                                </>
                            )}
                        </TouchableOpacity>
                    </View>
                </View>
            </ScrollView>
        </KeyboardAvoidingView>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1 },
    scrollContent: { flexGrow: 1 },
    headerWrapper: {
        width: '100%',
        paddingTop: 60,
        paddingHorizontal: 25,
        paddingBottom: 90,
        borderBottomLeftRadius: 35,
        borderBottomRightRadius: 35,
        overflow: 'hidden',
        borderCurve: 'continuous',
    },
    headerBackground: {
        position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    },
    backButton: {
        width: 40, height: 40, borderRadius: 20,
        backgroundColor: 'rgba(255,255,255,0.2)',
        justifyContent: 'center', alignItems: 'center',
        marginBottom: 20,
    },
    headerGreeting: { alignItems: 'flex-start' },
    greetingTitle: { color: '#FFF', fontSize: 28, fontWeight: '800', marginBottom: 6 },
    greetingSubtitle: { color: 'rgba(255,255,255,0.85)', fontSize: 15, fontWeight: '500' },
    contentWrapper: { paddingHorizontal: 20, marginTop: -65 },
    card: {
        borderRadius: 24, padding: 24,
        shadowColor: '#000', shadowOffset: { width: 0, height: 10 },
        shadowOpacity: 0.06, shadowRadius: 15, elevation: 8,
        borderCurve: 'continuous',
    },
    inputGroup: { marginBottom: 20 },
    label: { fontSize: 14, fontWeight: '600', marginBottom: 8 },
    inputRow: {
        flexDirection: 'row', alignItems: 'center',
        borderWidth: 1, borderRadius: 16,
        paddingHorizontal: 16, borderCurve: 'continuous',
    },
    input: { flex: 1, fontSize: 15, paddingVertical: 14 },
    eyeButton: { padding: 4 },
    button: {
        flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
        borderRadius: 16, paddingVertical: 16,
        marginTop: 8, borderCurve: 'continuous',
    },
    buttonText: { color: '#FFF', fontSize: 16, fontWeight: '700' },
});
