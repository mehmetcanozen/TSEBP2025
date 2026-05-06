import axios from 'axios';

// The EXPO_PUBLIC_ prefix is important for Expo to expose it to the app
export const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL || 'http://10.0.2.2:4000/api/v1';

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Example function to test connection
export const testBackendConnection = async () => {
  try {
    const response = await api.get('/health');
    console.log('Backend connected successfully!', response.data);
    return response.data;
  } catch (error) {
    console.error('Error connecting to backend:', error);
    throw error;
  }
};
