/**
 * Character Type Definitions
 * Production-grade typing for multi-character support
 */

export interface CharacterVoiceProfile {
  readonly id: string;
  readonly referenceId: string;
  readonly name: string;
  readonly accent: string;
  readonly speed: number; // Default speech rate
  readonly emotionalRange: Record<string, { speed: number }>;
}

export interface CharacterAnimationSet {
  readonly idle: string | null;
  readonly speaking: string | null;
  readonly thinking: string | null;
  readonly gesture?: string | null;
  readonly combat?: string | null;
}

export interface CharacterModel {
  readonly id: string;
  readonly path: string;
  readonly scale: number;
  readonly defaultPosition: { x: number; y: number; z: number };
  readonly defaultRotation: { x: number; y: number; z: number };
  readonly materialOverride?: {
    color: number;
    emissive: number;
    emissiveIntensity: number;
    opacity: number;
  };
}

export interface CharacterProfile {
  readonly id: string;
  readonly displayName: string;
  readonly model: CharacterModel;
  readonly voiceProfile: CharacterVoiceProfile;
  readonly animationSet: CharacterAnimationSet;
  readonly handTrackingEnabled: boolean;
  readonly description: string;
  readonly color: string; // HUD accent color (hex)
  
  // Future extensibility
  readonly systemPrompt?: string;
  readonly memoryStyle?: string;
  readonly emotionStyle?: string;
  readonly animationStyle?: string;
  readonly gestureStyle?: string;
  readonly colorTheme?: string;
  readonly particleTheme?: string;
  readonly cameraPreset?: string;
  readonly speechPreset?: string;
  readonly thinkingPreset?: string;
  readonly reasoningPreset?: string;
}

export interface CharacterState {
  currentCharacterId: string;
  scale: number;
  rotationY: number;
  visible: boolean;
}

export type CharacterChangeEvent = {
  previousCharacterId: string;
  newCharacterId: string;
  timestamp: number;
  reason: 'user-selection' | 'voice-command' | 'system';
};

export type ModelLoadError = {
  characterId: string;
  error: Error;
  fallbackToCharacterId?: string;
};
