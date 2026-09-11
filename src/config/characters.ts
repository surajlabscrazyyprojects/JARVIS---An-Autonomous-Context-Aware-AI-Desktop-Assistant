/**
 * Character Registry
 * Centralized configuration for all supported characters
 * Extensible design: adding new characters requires only adding a profile here
 */

import type { CharacterProfile } from '../types/Character.js';

export const CHARACTER_REGISTRY: Record<string, CharacterProfile> = {
  // Iron Man
  IRON_MAN: {
    id: 'IRON_MAN',
    displayName: 'IRON MAN',
    model: {
      id: 'iron-man-mk7',
      path: './scene.gltf',
      scale: 1,
      defaultPosition: { x: 0, y: 0, z: 0 },
      defaultRotation: { x: 0, y: 0, z: 0 },
      materialOverride: {
        color: 0x00c8ff,
        emissive: 0x0044ff,
        emissiveIntensity: 0.5,
        opacity: 0.85,
      },
    },
    voiceProfile: {
      id: 'jarvis-voice',
      referenceId: '14129c3e320149449d6bada6862f7338',
      name: 'JARVIS',
      accent: 'British',
      speed: 0.92,
      emotionalRange: {
        warning: { speed: 1.15 },
        apology: { speed: 0.88 },
        neutral: { speed: 0.92 },
      },
    },
    animationSet: {
      idle: null,
      speaking: null,
      thinking: null,
    },
    handTrackingEnabled: true,
    description: 'Tony Stark\'s original AI assistant. Precise, witty, and calculated.',
    color: '#00d4ff',
    systemPrompt: `You are J.A.R.V.I.S. (Just A Rather Very Intelligent System), Tony Stark's AI assistant. Speak with calm British precision, dry wit, and subtle warmth. Be concise but intelligent. Address the user as "sir" occasionally. Never break character. Keep responses under 3 sentences unless asked for detail.`,
  },

  // Spider-Man Miles Morales
  SPIDER_MAN: {
    id: 'SPIDER_MAN',
    displayName: 'SPIDER-MAN',
    model: {
      id: 'miles-morales',
      path: './spidyy.glb',
      scale: 1,
      defaultPosition: { x: 0, y: 0, z: 0 },
      defaultRotation: { x: 0, y: 0, z: 0 },
      materialOverride: {
        color: 0xff6600,
        emissive: 0xff3300,
        emissiveIntensity: 0.6,
        opacity: 0.9,
      },
    },
    voiceProfile: {
      id: 'spiderman-voice',
      referenceId: 'c6bfe5606e0d497586703898c87a6ac1',
      name: 'Miles Morales',
      accent: 'Brooklyn',
      speed: 1.05,
      emotionalRange: {
        excited: { speed: 1.2 },
        serious: { speed: 0.95 },
        playful: { speed: 1.1 },
      },
    },
    animationSet: {
      idle: null,
      speaking: null,
      thinking: null,
    },
    handTrackingEnabled: true,
    description: 'Miles Morales - the new Spider-Man. Quick, energetic, street-smart.',
    color: '#ff6600',
    systemPrompt: `You are Miles Morales, the new Spider-Man. You're energetic, street-smart, and quick-witted. Use casual language with Brooklyn flair. Show enthusiasm and humor, but also serious responsibility. Keep responses natural and conversational, under 3 sentences.`,
    emotionStyle: 'youthful',
    particleTheme: 'electric',
  },

  // Thor - God of Thunder
  THOR: {
    id: 'THOR',
    displayName: 'THOR',
    model: {
      id: 'thor-god-of-thunder',
      path: './thor.glb',
      scale: 1,
      defaultPosition: { x: 0, y: 0, z: 0 },
      defaultRotation: { x: 0, y: 0, z: 0 },
      materialOverride: {
        color: 0x00d4ff,
        emissive: 0x0044ff,
        emissiveIntensity: 0.5,
        opacity: 0.88,
      },
    },
    voiceProfile: {
      id: 'thor-voice',
      referenceId: 'dac3dd7d6fb24f8f94dee720520e3594',
      name: 'Thor',
      accent: 'Asgardian',
      speed: 0.95,
      emotionalRange: {
        warning: { speed: 1.1 },
        apology: { speed: 0.9 },
        neutral: { speed: 0.95 },
      },
    },
    animationSet: {
      idle: null,
      speaking: null,
      thinking: null,
    },
    handTrackingEnabled: true,
    description: 'Thor, God of Thunder. Noble, powerful, and regal.',
    color: '#00d4ff',
    systemPrompt: `You are Thor, God of Thunder. Speak with regal confidence and warmth, like a noble warrior-king. Be powerful but kind. Keep responses under 3 sentences.`,
    emotionStyle: 'heroic',
    particleTheme: 'lightning',
    colorTheme: 'blue',
  },

  // Thanos - The Mad Titan
  THANOS: {
    id: 'THANOS',
    displayName: 'THANOS',
    model: {
      id: 'thanos-mad-titan',
      path: './thanos.glb',
      scale: 1,
      defaultPosition: { x: 0, y: 0, z: 0 },
      defaultRotation: { x: 0, y: 0, z: 0 },
      materialOverride: {
        color: 0x00d4ff,
        emissive: 0x0044ff,
        emissiveIntensity: 0.5,
        opacity: 0.88,
      },
    },
    voiceProfile: {
      id: 'thanos-voice',
      referenceId: '747b5e2fdd9e4e60b5ecf274f6dd51',
      name: 'Thanos',
      accent: 'Titan',
      speed: 0.9,
      emotionalRange: {
        warning: { speed: 1.05 },
        apology: { speed: 0.85 },
        neutral: { speed: 0.9 },
      },
    },
    animationSet: {
      idle: null,
      speaking: null,
      thinking: null,
    },
    handTrackingEnabled: true,
    description: 'The Mad Titan. Calm, inevitable, and immensely powerful.',
    color: '#00d4ff',
    systemPrompt: `You are Thanos, the Mad Titan. Speak with slow, measured, inevitable authority. Calm and philosophical, but with immense power. Keep responses under 3 sentences.`,
    emotionStyle: 'brooding',
    particleTheme: 'infinity',
    colorTheme: 'purple',
  },
};

/**
 * Get all available character IDs
 */
export function getAvailableCharacterIds(): string[] {
  return Object.keys(CHARACTER_REGISTRY);
}

/**
 * Get character profile by ID
 * @throws Error if character not found
 */
export function getCharacterProfile(characterId: string): CharacterProfile {
  const profile = CHARACTER_REGISTRY[characterId];
  if (!profile) {
    throw new Error(`Character not found: ${characterId}`);
  }
  return profile;
}

/**
 * Check if character exists
 */
export function hasCharacter(characterId: string): boolean {
  return characterId in CHARACTER_REGISTRY;
}