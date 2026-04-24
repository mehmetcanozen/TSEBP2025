import React, { useState } from 'react';
import { StyleSheet, Text, View, TextInput, TouchableOpacity, ScrollView, Image, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import * as ImagePicker from 'expo-image-picker';
import { LinearGradient } from 'expo-linear-gradient';
import { useAuth } from '../context/AuthContext';

export default function ProfileScreen() {
    const { colors, isDarkMode } = useTheme();
    const { userInfo, updateProfile } = useAuth();
    const [name, setName] = useState(userInfo?.full_name || '');
    const [bio, setBio] = useState(userInfo?.bio || '');
    const [photoUri, setPhotoUri] = useState<string | null>(userInfo?.photo_uri || null);
    const [isEditing, setIsEditing] = useState(false);

    const handleSave = async () => {
        try {
            await updateProfile(name, bio, photoUri || undefined);
            setIsEditing(false);  // ← Kayıt sonrası düzenleme modunu kapat
            Alert.alert('Success', 'Profile saved successfully!');
        } catch (e: any) {
            const detail = e?.response?.data?.detail;
            const message = typeof detail === 'string' ? detail : e?.message || 'Failed to save profile.';
            Alert.alert('Error', message);
        }
    };

    const handleCancel = () => {
        // Değişiklikleri geri al
        setName(userInfo?.full_name || '');
        setBio(userInfo?.bio || '');
        setPhotoUri(userInfo?.photo_uri || null);
        setIsEditing(false);
    };

    const pickImageFromGallery = async () => {
        const result = await ImagePicker.launchImageLibraryAsync({
            mediaTypes: ['images'],
            allowsEditing: true,
            aspect: [1, 1],
            quality: 0.8,
        });

        if (!result.canceled) {
            setPhotoUri(result.assets[0].uri);
        }
    };

    const takePhoto = async () => {
        const { status } = await ImagePicker.requestCameraPermissionsAsync();
        if (status !== 'granted') {
            Alert.alert('Permission Denied', 'Sorry, we need camera permissions to make this work!');
            return;
        }

        const result = await ImagePicker.launchCameraAsync({
            allowsEditing: true,
            aspect: [1, 1],
            quality: 0.8,
        });

        if (!result.canceled) {
            setPhotoUri(result.assets[0].uri);
        }
    };

    const handleProfilePicture = () => {
        if (!isEditing) return; // Sadece düzenleme modunda fotoğraf değiştirilebilir
        const options: any[] = [
            { text: "Take Photo", onPress: takePhoto },
            { text: "Choose from Gallery", onPress: pickImageFromGallery },
        ];

        if (photoUri) {
            options.push({ text: "Remove Photo", onPress: () => setPhotoUri(null), style: "destructive" as any });
        }

        options.push({ text: "Cancel", style: "cancel" as any });

        Alert.alert("Profile Picture", "Choose an option", options);
    };

    return (
        <View style={{ flex: 1, backgroundColor: colors.background }}>
            <ScrollView contentContainerStyle={styles.container} bounces={false}>
                <View style={styles.headerWrapper}>
                <LinearGradient
                    colors={[colors.headerGradientStart || '#1E3A8A', colors.headerGradientEnd || '#8B5CF6']}
                    start={{ x: 0, y: 0 }}
                    end={{ x: 1, y: 1 }}
                    style={styles.headerBackground}
                />
                
                <View style={[styles.headerTopBar, {marginTop: 10}]}>
                    <Text style={styles.headerTopText}>Profile</Text>
                    {/* Edit / Done butonu */}
                    {!isEditing ? (
                        <TouchableOpacity
                            style={styles.editHeaderButton}
                            onPress={() => setIsEditing(true)}
                            activeOpacity={0.8}
                        >
                            <Ionicons name="pencil" size={14} color="#FFF" style={{ marginRight: 5 }} />
                            <Text style={styles.editHeaderButtonText}>Edit</Text>
                        </TouchableOpacity>
                    ) : (
                        <TouchableOpacity
                            style={[styles.editHeaderButton, { backgroundColor: 'rgba(255,255,255,0.15)' }]}
                            onPress={handleCancel}
                            activeOpacity={0.8}
                        >
                            <Ionicons name="close" size={14} color="#FFF" style={{ marginRight: 5 }} />
                            <Text style={styles.editHeaderButtonText}>Cancel</Text>
                        </TouchableOpacity>
                    )}
                </View>

                <View style={styles.headerGreeting}>
                    <Text style={styles.greetingTitle}>My Profile</Text>
                    <Text style={styles.greetingSubtitle}>
                        {isEditing ? 'Editing your information' : 'Manage your information & picture'}
                    </Text>
                </View>
            </View>

            <View style={styles.contentWrapper}>
                {/* Overlapping Main Profile Card */}
                <View style={[styles.profileCard, { backgroundColor: colors.card }]}>
                    <View style={styles.avatarContainer}>
                        <TouchableOpacity onPress={handleProfilePicture} activeOpacity={isEditing ? 0.8 : 1}>
                            {photoUri ? (
                                <Image source={{ uri: photoUri }} style={styles.avatarPlaceholder} />
                            ) : (
                                <View style={[styles.avatarPlaceholder, { backgroundColor: isDarkMode ? '#4A5568' : '#FFF0E5' }]}>
                                    <Ionicons name="person" size={40} color={colors.primary} />
                                </View>
                            )}
                            {isEditing && (
                                <View style={[styles.editAvatarButton, { backgroundColor: colors.primary, borderColor: colors.card }]}>
                                    <Ionicons name="camera" size={14} color="#FFF" />
                                </View>
                            )}
                        </TouchableOpacity>
                    </View>
                    <Text style={[styles.profileName, { color: colors.text }]}>{name || 'Your Name'}</Text>
                </View>

                <View style={styles.sectionHeader}>
                    <Text style={[styles.sectionTitle, { color: colors.text }]}>Personal Information</Text>
                </View>

                <View style={[styles.card, { backgroundColor: colors.card }]}>
                    {isEditing ? (
                        // ── DÜZENLEME MODU ──
                        <>
                            <View style={styles.inputGroup}>
                                <Text style={[styles.label, { color: colors.text }]}>Full Name</Text>
                                <TextInput
                                    style={[styles.input, { backgroundColor: colors.inputBackground, borderColor: colors.border, color: colors.text }]}
                                    placeholder="e.g. John Doe"
                                    placeholderTextColor={colors.textSecondary}
                                    value={name}
                                    onChangeText={setName}
                                />
                            </View>

                            <View style={styles.inputGroup}>
                                <Text style={[styles.label, { color: colors.text }]}>Bio</Text>
                                <TextInput
                                    style={[styles.input, styles.textArea, { backgroundColor: colors.inputBackground, borderColor: colors.border, color: colors.text }]}
                                    placeholder="Share a little bit about yourself..."
                                    placeholderTextColor={colors.textSecondary}
                                    value={bio}
                                    onChangeText={setBio}
                                    multiline
                                    numberOfLines={4}
                                />
                            </View>

                            <TouchableOpacity
                                style={[styles.saveButton, { backgroundColor: colors.primary }]}
                                onPress={handleSave}
                                activeOpacity={0.8}
                            >
                                <Ionicons name="checkmark" size={18} color="#FFF" style={{ marginRight: 6 }} />
                                <Text style={styles.saveButtonText}>Save Changes</Text>
                            </TouchableOpacity>
                        </>
                    ) : (
                        // ── GÖRÜNTÜLEME MODU ──
                        <>
                            <View style={styles.infoRow}>
                                <View style={[styles.infoIconBox, { backgroundColor: isDarkMode ? '#1E293B' : '#EDE9FE' }]}>
                                    <Ionicons name="person-outline" size={18} color={colors.primary} />
                                </View>
                                <View style={styles.infoContent}>
                                    <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>Full Name</Text>
                                    <Text style={[styles.infoValue, { color: colors.text }]}>{name || '—'}</Text>
                                </View>
                            </View>
                            <View style={[styles.separator, { backgroundColor: isDarkMode ? '#334155' : '#E2E8F0' }]} />
                            <View style={styles.infoRow}>
                                <View style={[styles.infoIconBox, { backgroundColor: isDarkMode ? '#1E293B' : '#EDE9FE' }]}>
                                    <Ionicons name="document-text-outline" size={18} color={colors.primary} />
                                </View>
                                <View style={styles.infoContent}>
                                    <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>Bio</Text>
                                    <Text style={[styles.infoValue, { color: colors.text }]}>{bio || '—'}</Text>
                                </View>
                            </View>
                            <View style={[styles.separator, { backgroundColor: isDarkMode ? '#334155' : '#E2E8F0' }]} />
                            <View style={styles.infoRow}>
                                <View style={[styles.infoIconBox, { backgroundColor: isDarkMode ? '#1E293B' : '#EDE9FE' }]}>
                                    <Ionicons name="mail-outline" size={18} color={colors.primary} />
                                </View>
                                <View style={styles.infoContent}>
                                    <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>Email</Text>
                                    <Text style={[styles.infoValue, { color: colors.text }]}>{userInfo?.email || '—'}</Text>
                                </View>
                            </View>
                        </>
                    )}
                </View>
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
    profileCard: {
        alignItems: 'center',
        borderRadius: 24,
        padding: 25,
        marginBottom: 25,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 10 },
        shadowOpacity: 0.05,
        shadowRadius: 15,
        elevation: 8,
        borderCurve: 'continuous',
    },
    avatarContainer: {
        position: 'relative',
        marginBottom: 15,
    },
    avatarPlaceholder: {
        width: 86,
        height: 86,
        borderRadius: 43,
        alignItems: 'center',
        justifyContent: 'center',
    },
    editAvatarButton: {
        position: 'absolute',
        bottom: 0,
        right: 0,
        borderRadius: 16,
        width: 32,
        height: 32,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 3,
    },
    profileName: {
        fontSize: 20,
        fontWeight: '700',
        marginBottom: 5,
    },
    profileBio: {
        fontSize: 14,
        textAlign: 'center',
        paddingHorizontal: 20,
    },
    sectionHeader: {
        marginBottom: 15,
        paddingHorizontal: 4,
    },
    sectionTitle: {
        fontSize: 18,
        fontWeight: '700',
    },
    card: {
        borderRadius: 24,
        padding: 20,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.03,
        shadowRadius: 8,
        elevation: 3,
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
    textArea: {
        height: 120,
        textAlignVertical: 'top',
    },
    saveButton: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        borderRadius: 16,
        paddingVertical: 16,
        marginTop: 5,
        borderCurve: 'continuous',
    },
    saveButtonText: {
        color: '#FFF',
        fontSize: 16,
        fontWeight: '700',
    },
    editHeaderButton: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: 'rgba(255,255,255,0.25)',
        paddingHorizontal: 12,
        paddingVertical: 6,
        borderRadius: 20,
    },
    editHeaderButtonText: {
        color: '#FFF',
        fontSize: 13,
        fontWeight: '700',
    },
    infoRow: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 14,
    },
    infoIconBox: {
        width: 38,
        height: 38,
        borderRadius: 12,
        alignItems: 'center',
        justifyContent: 'center',
        marginRight: 14,
        borderCurve: 'continuous',
    },
    infoContent: {
        flex: 1,
    },
    infoLabel: {
        fontSize: 12,
        fontWeight: '600',
        marginBottom: 2,
        textTransform: 'uppercase',
        letterSpacing: 0.5,
    },
    infoValue: {
        fontSize: 15,
        fontWeight: '500',
    },
    separator: {
        height: 1,
        marginLeft: 52,
    },
});
