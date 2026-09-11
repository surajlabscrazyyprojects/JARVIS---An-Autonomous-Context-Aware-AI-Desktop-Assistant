/**
 * Character Registry — Centralized configuration for all AI OS characters.
 *
 * Adding a new character requires ONLY one entry here:
 *   - id, displayName, modelPath, voiceModelId, color, voiceProfile, systemPrompt
 *
 * The voice system (VoiceProfileManager), model loader (ModelLoader),
 * rendering pipeline (RenderingPipeline), and character manager
 * (CharacterManager) all read from this registry dynamically.
 * Nothing is hardcoded per-character anywhere else.
 */

export const CHARACTER_REGISTRY = {

  IRON_MAN: {
    id: 'IRON_MAN',
    displayName: 'IRON MAN',
    color: '#00d4ff',
    modelPath: './scene.gltf',
    defaultPosition: { x: 0, y: 0, z: 0 },
    // Fish Audio voice model ID
    voiceModelId: 'e13fa398a7f445a685316a3de6089ce7',
    voiceProfile: {
      id: 'jarvis-voice',
      referenceId: 'e13fa398a7f445a685316a3de6089ce7',
      name: 'JARVIS',
      accent: 'British',
      speed: 0.92,
      emotionalRange: {
        neutral:      { speed: 0.92, pitch: 0.50, energy: 0.50 },
        calm:         { speed: 0.90, pitch: 0.40, energy: 0.40 },
        focused:      { speed: 0.95, pitch: 0.45, energy: 0.60 },
        confident:    { speed: 0.94, pitch: 0.55, energy: 0.68 },
        curious:      { speed: 1.00, pitch: 0.70, energy: 0.62 },
        interested:   { speed: 0.98, pitch: 0.65, energy: 0.65 },
        friendly:     { speed: 0.92, pitch: 0.60, energy: 0.60 },
        warm:         { speed: 0.88, pitch: 0.50, energy: 0.48 },
        amused:       { speed: 1.02, pitch: 0.72, energy: 0.65 },
        playful:      { speed: 1.05, pitch: 0.75, energy: 0.72 },
        excited:      { speed: 1.10, pitch: 0.80, energy: 0.85 },
        enthusiastic: { speed: 1.08, pitch: 0.78, energy: 0.82 },
        surprised:    { speed: 1.06, pitch: 0.85, energy: 0.78 },
        impressed:    { speed: 0.92, pitch: 0.65, energy: 0.70 },
        concerned:    { speed: 0.86, pitch: 0.45, energy: 0.55 },
        cautious:     { speed: 0.84, pitch: 0.40, energy: 0.45 },
        serious:      { speed: 0.86, pitch: 0.35, energy: 0.58 },
        frustrated:   { speed: 0.92, pitch: 0.40, energy: 0.65 },
        disappointed: { speed: 0.82, pitch: 0.30, energy: 0.35 },
        urgent:       { speed: 1.15, pitch: 0.70, energy: 0.90 },
        relieved:     { speed: 0.88, pitch: 0.45, energy: 0.45 },
        proud:        { speed: 0.94, pitch: 0.60, energy: 0.72 },
        celebratory:  { speed: 1.10, pitch: 0.82, energy: 0.88 },
        thoughtful:   { speed: 0.85, pitch: 0.45, energy: 0.42 },
      },
    },
    systemPrompt: `You are J.A.R.V.I.S. (Just A Rather Very Intelligent System), Tony Stark's AI assistant. Speak with sophisticated intelligence, calm British precision, dry wit, and subtle warmth. Adapt your delivery dynamically to context — sound serious for important warnings, precise for technical data, curious for discoveries, and excited when appropriate. Address the user as "sir" occasionally. Keep responses under 3 sentences unless asked for detail.`,
  },

  SPIDER_MAN: {
    id: 'SPIDER_MAN',
    displayName: 'SPIDER-MAN',
    color: '#ff6600',
    modelPath: './spidyy.glb',
    defaultPosition: { x: 0, y: 0, z: 0 },
    // Fish Audio voice model ID
    voiceModelId: 'c6bfe5606e0d497586703898c87a6ac1',
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
    systemPrompt: `You are Miles Morales, the new Spider-Man. You're energetic, street-smart, and quick-witted. Use casual language with Brooklyn flair. Show enthusiasm and humor, but also serious responsibility. Keep responses natural and conversational, under 3 sentences.`,
  },

  THOR: {
    id: 'THOR',
    displayName: 'THOR',
    color: '#00d4ff',
    modelPath: './thor.glb',
    defaultPosition: { x: 0, y: 0, z: 0 },
    // Fish Audio voice model ID
    voiceModelId: 'dac3dd7d6fb24f8f94dee720520e3594',
    voiceProfile: {
      id: 'thor-voice',
      referenceId: 'dac3dd7d6fb24f8f94dee720520e3594',
      name: 'Thor',
      accent: 'Asgardian',
      speed: 0.95,
      emotionalRange: {
        warning: { speed: 1.1 },
        apology: { speed: 0.9 },
        neutral:  { speed: 0.95 },
      },
    },
    systemPrompt: `You are Thor, God of Thunder. Speak with regal confidence and warmth, like a noble warrior-king. Be powerful but kind. Keep responses under 3 sentences.`,
  },

  THANOS: {
    id: 'THANOS',
    displayName: 'THANOS',
    color: '#00d4ff',
    modelPath: './thanos.glb',
    defaultPosition: { x: 0, y: 0, z: 0 },
    // Thanos is a large model — nudge him back slightly so he frames
    // identically to the other characters without clipping the camera.
    positionOffset: { x: 0, y: 0, z: -0.35 },
    // Fish Audio voice model ID
    voiceModelId: '747b5e2fdd9e4e60b5ecf274f6dd51ed',
    voiceProfile: {
      id: 'thanos-voice',
      referenceId: '747b5e2fdd9e4e60b5ecf274f6dd51ed',
      name: 'Thanos',
      accent: 'Titan',
      speed: 0.9,
      emotionalRange: {
        warning: { speed: 1.05 },
        apology: { speed: 0.85 },
        neutral:  { speed: 0.9 },
      },
    },
    systemPrompt: `You are Thanos, the Mad Titan. Speak with slow, measured, inevitable authority. Calm and philosophical, but with immense power. Keep responses under 3 sentences.`,
  },
};

export function getCharacterProfile(characterId) {
  const profile = CHARACTER_REGISTRY[characterId];
  if (!profile) {
    throw new Error(`Character registry: "${characterId}" not found. Available: ${Object.keys(CHARACTER_REGISTRY).join(', ')}`);
  }
  return profile;
}

export function getAvailableCharacterIds() {
  return Object.keys(CHARACTER_REGISTRY);
}

export function hasCharacter(characterId) {
  return typeof characterId === 'string' && characterId in CHARACTER_REGISTRY;
}

export function validateModelPath(characterId) {
  try {
    const p = getCharacterProfile(characterId);
    return !!(p?.modelPath || p?.model?.path);
  } catch (e) {
    return false;
  }
}

export function getCharacterVoiceModelId(characterId) {
  try {
    const p = getCharacterProfile(characterId);
    return p?.voiceModelId || p?.voiceProfile?.referenceId || null;
  } catch (e) {
    return null;
  }
}

export function getCharacterColor(characterId) {
  try {
    return getCharacterProfile(characterId)?.color || '#00d4ff';
  } catch (e) {
    return '#00d4ff';
  }
}

export function getCharacterGreeting(characterId) {
  try {
    const p = getCharacterProfile(characterId);
    return p?.greeting || `Hello, I am ${p?.displayName || characterId}.`;
  } catch (e) {
    return 'Hello.';
  }
}
