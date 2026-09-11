/**
 * Voice Profile Manager (JavaScript)
 * Manages character-specific voice profiles and TTS configuration
 * Never hardcodes voice IDs - always derives from centralized character registry
 */

/**
 * @class VoiceProfileManager
 */
import { CHARACTER_REGISTRY as _StaticRegistry, getCharacterProfile as _staticGetProfile } from '../config/characters.js';
export class VoiceProfileManager {
  constructor() {
    this.currentProfile = null;
    this.currentCharacterId = null;
    this.emotionCache = new Map();
  }

  /**
   * Set active character voice profile
   * @param {Object} profile - CharacterVoiceProfile
   */
  setActiveProfile(profile) {
    if (!profile) {
      console.error('Invalid voice profile provided');
      return;
    }
    this.currentProfile = profile;
    this.emotionCache.clear();
    console.log(`✓ Voice profile set: ${profile.name} (${profile.accent})`);
  }

  /**
   * Set active character by ID — loads voice profile from centralized registry.
   * Automatically switches the Fish Audio voice model instantly.
   * @param {string} characterId - Character ID from CHARACTER_REGISTRY
   * @param {Object|null} registry - Optional injected registry
   * @returns {Object|null} The active voice profile
   */
  setActiveCharacter(characterId, registry) {
    if (!characterId) {
      console.error('Invalid character ID provided');
      return null;
    }

    // Lazy-load the centralized registry to avoid circular imports
    // FIX (2026-09-03): require() is not available in browser ES modules. Use static import fallback.
    let registryModule = registry;
    if (!registryModule) {
      try {
        // In ES module context, use dynamic import if available, otherwise fallback to global registry
        // We already have CHARACTER_REGISTRY available via static import in some contexts,
        // but to avoid circular import issues we try to load it gracefully.
        // The CharacterManager already imports it statically, so we can retrieve via window if needed.
        // First try to use the statically imported module if this file is ever imported with it.
        // For now, attempt to use window.__characterRegistry if available, otherwise import.
        if (typeof window !== 'undefined' && window.__characterRegistry) {
          registryModule = window.__characterRegistry;
        } else {
          // Use statically imported registry (proper ES module, no require)
          console.log('[VoiceProfileManager] Using statically imported CHARACTER_REGISTRY');
          registryModule = {
            getCharacterProfile: _staticGetProfile,
            CHARACTER_REGISTRY: _StaticRegistry
          };
        }
      } catch (e) {
        console.warn('[VoiceProfileManager] Could not load character registry:', e);
        return null;
      }
    }

    const profile = registryModule.getCharacterProfile
      ? registryModule.getCharacterProfile(characterId)
      : registryModule.CHARACTER_REGISTRY?.[characterId];

    if (!profile) {
      console.error(`Character "${characterId}" not found in registry`);
      return null;
    }

    this.currentCharacterId = characterId;
    this.currentProfile = profile.voiceProfile
      ? { ...profile.voiceProfile }
      : {
          id: `${characterId.toLowerCase()}-voice`,
          referenceId: profile.voiceModelId,
          name: profile.displayName,
          accent: 'default',
          speed: 0.95,
          emotionalRange: {},
        };
    // Ensure referenceId is always the Fish Audio voiceModelId
    if (profile.voiceModelId) {
      this.currentProfile.referenceId = profile.voiceModelId;
    }
    this.emotionCache.clear();
    console.log(`✓ Voice switched to ${profile.displayName} (model: ${this.currentProfile.referenceId})`);
    return this.currentProfile;
  }

  /**
   * Get current active character ID
   * @returns {string|null}
   */
  getActiveCharacterId() {
    return this.currentCharacterId;
  }

  /**
   * Get current active profile
   * @returns {Object|null}
   */
  getActiveProfile() {
    return this.currentProfile;
  }

  /**
   * Detect emotion from text and return speed modifier
   * Uses character's emotional range if available
   * @param {string} text
   * @returns {{speed: number}}
   */
  /**
   * Detect emotion from text and return prosody modifiers
   * Uses character's emotional range if available
   * @param {string} text
   * @param {Object} [metaOverride]
   * @returns {{speed: number, pitch?: number, energy?: number, emotion: string}}
   */
  detectEmotion(text, metaOverride) {
    if (metaOverride && metaOverride.emotion) {
      const emotionalRange = this.currentProfile?.emotionalRange || {};
      const base = emotionalRange[metaOverride.emotion] || {};
      return {
        emotion: metaOverride.emotion,
        speed: metaOverride.speaking_rate || base.speed || this.currentProfile?.speed || 0.92,
        pitch: metaOverride.pitch_variation || base.pitch || 0.5,
        energy: metaOverride.energy || base.energy || 0.5,
      };
    }

    if (!this.currentProfile) {
      return { emotion: 'calm', speed: 0.92, pitch: 0.5, energy: 0.5 };
    }

    const t = text.toLowerCase();
    const emotionalRange = this.currentProfile.emotionalRange || {};

    const keywordMap = {
      urgent: /warning|alert|danger|critical|threat|stop|halt|emergency/i,
      concerned: /sorry|apolog|unfortunate|regret|error|failed/i,
      excited: /excellent|perfect|outstanding|brilliant|amazing|awesome|yay/i,
      surprised: /wait\.\.\.|hold on\.\.\.|seriously\?/i,
      amused: /haha|hehe|jokes|funny|fun|ironic/i,
      serious: /serious|urgent|important|now|critical/i,
      calm: /relax|easy|simple|peace|calm/i,
      curious: /curious|interesting|investigating|inspecting/i,
      focused: /analyzing|processing|working|executing/i,
    };

    for (const [emotion, regex] of Object.entries(keywordMap)) {
      if (regex.test(t) && emotion in emotionalRange) {
        return { emotion, ...emotionalRange[emotion] };
      }
    }

    return { emotion: 'calm', speed: this.currentProfile.speed, pitch: 0.5, energy: 0.5 };
  }

  /**
   * Build Fish Audio TTS request configuration
   * Dynamic based on current character profile & emotional metadata
   * @param {string} text
   * @param {Object} [metadata]
   * @returns {Object} VoiceConfig
   */
  buildTTSConfig(text, metadata) {
    if (!this.currentProfile) {
      throw new Error('No active voice profile set');
    }

    const prosodyMeta = this.detectEmotion(text, metadata);

    return {
      referenceId: this.currentProfile.referenceId,
      format: 'mp3',
      mp3Bitrate: 128,
      normalize: true,
      latency: 'normal',
      prosody: {
        speed: prosodyMeta.speed,
        volume: 0,
      },
      emotionMetadata: metadata || prosodyMeta,
    };
  }

  /**
   * Build complete Fish Audio API request body
   * @param {string} text
   * @returns {Object}
   */
  buildTTSRequestBody(text) {
    const config = this.buildTTSConfig(text);
    return {
      text,
      reference_id: config.referenceId,
      format: config.format,
      mp3_bitrate: config.mp3Bitrate,
      normalize: config.normalize,
      latency: config.latency,
      prosody: config.prosody,
    };
  }

  /**
   * Validate voice profile has required fields
   * @param {Object|null} profile
   * @returns {boolean}
   */
  isProfileValid(profile) {
    if (!profile) return false;
    return !!(
      profile.id &&
      profile.referenceId &&
      profile.name &&
      typeof profile.speed === 'number'
    );
  }

  /**
   * Get voice description (for logging/UI)
   * @returns {string}
   */
  getVoiceDescription() {
    if (!this.currentProfile) {
      return 'No voice profile active';
    }
    return `${this.currentProfile.name} (${this.currentProfile.accent})`;
  }

  /**
   * Clear active profile
   */
  clear() {
    this.currentProfile = null;
    this.emotionCache.clear();
  }
}

// Singleton instance
let instance = null;

/**
 * Get or create singleton instance
 * @returns {VoiceProfileManager}
 */
export function getVoiceProfileManager() {
  if (!instance) {
    instance = new VoiceProfileManager();
  }
  return instance;
}
