export interface Exact15Category {
  id: string;
  label: string;
  icon: string;
  defaultAggressiveness: number;
  transient: boolean;
}

export const EXACT15_CATEGORIES: Exact15Category[] = [
  { id: 'speech', label: 'Speech', icon: 'mic-outline', defaultAggressiveness: 1.4, transient: false },
  { id: 'music', label: 'Music', icon: 'musical-notes-outline', defaultAggressiveness: 1.5, transient: false },
  { id: 'dog barking', label: 'Dog Bark', icon: 'paw-outline', defaultAggressiveness: 1.9, transient: false },
  { id: 'car engine', label: 'Car Engine', icon: 'car-outline', defaultAggressiveness: 1.8, transient: false },
  { id: 'footsteps', label: 'Footsteps', icon: 'footsteps-outline', defaultAggressiveness: 1.5, transient: false },
  { id: 'rain', label: 'Rain', icon: 'rainy-outline', defaultAggressiveness: 1.3, transient: false },
  { id: 'wind', label: 'Wind', icon: 'leaf-outline', defaultAggressiveness: 1.6, transient: false },
  { id: 'keyboard typing', label: 'Keyboard', icon: 'keypad-outline', defaultAggressiveness: 2.2, transient: true },
  { id: 'phone ringing', label: 'Phone', icon: 'notifications-outline', defaultAggressiveness: 2.0, transient: false },
  { id: 'crowd noise', label: 'Crowd', icon: 'people-outline', defaultAggressiveness: 1.5, transient: false },
  { id: 'bird singing', label: 'Birds', icon: 'color-filter-outline', defaultAggressiveness: 1.5, transient: false },
  { id: 'water flowing', label: 'Water', icon: 'water-outline', defaultAggressiveness: 1.4, transient: false },
  { id: 'door knocking', label: 'Knocking', icon: 'log-in-outline', defaultAggressiveness: 2.0, transient: true },
  { id: 'alarm', label: 'Alarm', icon: 'alarm-outline', defaultAggressiveness: 2.3, transient: true },
  { id: 'background noise', label: 'Background', icon: 'volume-mute-outline', defaultAggressiveness: 1.2, transient: false },
];

export const EXACT15_CATEGORY_BY_ID = new Map(
  EXACT15_CATEGORIES.map((category) => [category.id, category] as const)
);
