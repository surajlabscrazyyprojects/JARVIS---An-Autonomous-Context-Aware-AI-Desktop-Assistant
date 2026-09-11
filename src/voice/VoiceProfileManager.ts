/**
 * Voice Profile Manager
 * Manages character-specific voice profiles and TTS configuration
 * Never hardcodes voice IDs - always derives from active character profile
 */

import type { CharacterVoiceProfile } from '../types/Character.js';

export interface VoiceConfig {
  referenceId: string;
  format: 'mp3';
  mp3Bitrate: number;
  normalize: boolean;
  latency: 'normal' | 'fast' | 'best';
  prosody: {
    speed: number;
    volume: number;
  };
}

export class VoiceProfileManager {
  private currentProfile: CharacterVoiceProfile | null = null;
  private emotionCache: Map<string, number> = new Map();
  
  /**
   * Set active character voice profile
   */
  setActiveProfile(profile: CharacterVoiceProfile): void {
    if (!profile) {
      console.error('Invalid voice profile provided');
      return;
    }
    this.currentProfile = profile;
    this.emotionCache.clear();
  }

  /**
   * Get current active profile
   */
  getActiveProfile(): CharacterVoiceProfile | null {
    return this.currentProfile;
  }

  /**
   * Detect emotion from text and return speed modifier
   * Uses character's emotional range if available
   */
  /**
   * Detect emotion from text and return prosody modifiers
   * Uses character's emotional range if available
   */
  detectEmotion(text: string, metaOverride?: any): { speed: number; pitch?: number; energy?: number; emotion: string } {
    if (metaOverride && metaOverride.emotion) {
      const emotionalRange = this.currentProfile?.emotionalRange || {};
      const base = (emotionalRange as any)[metaOverride.emotion] || {};
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

    const keywordMap: Record<string, RegExp> = {
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
        return { emotion, ...(emotionalRange as any)[emotion] };
      }
    }

    return { emotion: 'calm', speed: this.currentProfile.speed, pitch: 0.5, energy: 0.5 };
  }

  /**
   * Build Fish Audio TTS request configuration
   * Dynamic based on current character profile & emotional metadata
   */
  buildTTSConfig(text: string, metadata?: any): VoiceConfig {
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
    };
  }

  /**
   * Build complete Fish Audio API request body
   */
  buildTTSRequestBody(text: string, metadata?: any): Record<string, any> {
    const config = this.buildTTSConfig(text, metadata);
    return {
      text,
      reference_id: config.referenceId,
      format: config.format,
      mp3_bitrate: config.mp3Bitrate,
      normalize: config.normalize,
      latency: config.latency,
      prosody: config.prosody,
      emotion_metadata: metadata,
    };
  }

  /**
   * Validate voice profile has required fields
   */
  isProfileValid(profile: CharacterVoiceProfile | null): boolean {
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
   */
  getVoiceDescription(): string {
    if (!this.currentProfile) {
      return 'No voice profile active';
    }
    return `${this.currentProfile.name} (${this.currentProfile.accent})`;
  }

  /**
   * Clear active profile
   */
  clear(): void {
    this.currentProfile = null;
    this.emotionCache.clear();
  }
}

// Singleton instance
let instance: VoiceProfileManager | null = null;

/**
 * Get or create singleton instance
 */
export function getVoiceProfileManager(): VoiceProfileManager {
  if (!instance) {
    instance = new VoiceProfileManager();
  }
  return instance;
}
