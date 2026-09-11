/**
 * Character Manager
 * Single source of truth for character state, model management, and transitions
 * Handles character switching, state preservation, and event dispatching
 */

import type { 
  CharacterProfile, 
  CharacterState, 
  CharacterChangeEvent,
  ModelLoadError 
} from '../types/Character.js';
import { CHARACTER_REGISTRY, getCharacterProfile } from '../config/characters.js';
import { getVoiceProfileManager } from '../voice/VoiceProfileManager.js';

export type CharacterEventType = 'character-change' | 'character-loaded' | 'character-error' | 'state-updated';

export type CharacterEventListener = (
  type: CharacterEventType,
  data: CharacterChangeEvent | CharacterProfile | ModelLoadError | CharacterState
) => void;

export class CharacterManager {
  private currentCharacterId: string = 'IRON_MAN';
  private availableCharacterIds: string[] = Object.keys(CHARACTER_REGISTRY);
  private characterState: Map<string, CharacterState> = new Map();
  private eventListeners: Set<CharacterEventListener> = new Set();
  private loadedModels: Map<string, THREE.Group | null> = new Map();
  private isTransitioning: boolean = false;

  constructor() {
    // Initialize state for all characters
    this.availableCharacterIds.forEach((id) => {
      this.characterState.set(id, {
        currentCharacterId: id,
        scale: 1.0,
        rotationY: 0,
        visible: id === 'IRON_MAN',
      });
      this.loadedModels.set(id, null);
    });

    // Initialize voice profile for current character
    const profile = getCharacterProfile('IRON_MAN');
    getVoiceProfileManager().setActiveProfile(profile.voiceProfile);
  }

  /**
   * Get current active character ID
   */
  getCurrentCharacterId(): string {
    return this.currentCharacterId;
  }

  /**
   * Get current character profile
   */
  getCurrentCharacterProfile(): CharacterProfile {
    return getCharacterProfile(this.currentCharacterId);
  }

  /**
   * Get all available character IDs
   */
  getAvailableCharacterIds(): string[] {
    return [...this.availableCharacterIds];
  }

  /**
   * Switch to a different character
   * Preserves state, updates voice profile, emits events
   */
  async switchCharacter(
    characterId: string,
    reason: 'user-selection' | 'voice-command' | 'system' = 'user-selection'
  ): Promise<void> {
    // Validation
    if (!this.availableCharacterIds.includes(characterId)) {
      throw new Error(`Character not found: ${characterId}`);
    }

    if (this.currentCharacterId === characterId) {
      console.debug(`Already on character: ${characterId}`);
      return;
    }

    if (this.isTransitioning) {
      console.warn('Character transition in progress, queuing request');
      await new Promise((resolve) => setTimeout(resolve, 500));
    }

    this.isTransitioning = true;

    try {
      const previousCharacterId = this.currentCharacterId;
      const newProfile = getCharacterProfile(characterId);

      // Update voice profile for new character
      getVoiceProfileManager().setActiveProfile(newProfile.voiceProfile);

      // Update current character ID
      this.currentCharacterId = characterId;

      // Emit character change event
      this.emit('character-change', {
        previousCharacterId,
        newCharacterId: characterId,
        timestamp: Date.now(),
        reason,
      } as CharacterChangeEvent);

      // Emit loaded event
      this.emit('character-loaded', newProfile);

      console.log(`✓ Switched to character: ${characterId}`);
    } finally {
      this.isTransitioning = false;
    }
  }

  /**
   * Update character-specific state (scale, rotation, etc.)
   */
  updateCharacterState(characterId: string, updates: Partial<CharacterState>): void {
    const state = this.characterState.get(characterId);
    if (!state) {
      console.error(`Character state not found: ${characterId}`);
      return;
    }

    const updated = { ...state, ...updates };
    this.characterState.set(characterId, updated);
    this.emit('state-updated', updated);
  }

  /**
   * Get character state (scale, rotation, visibility)
   */
  getCharacterState(characterId: string): CharacterState | null {
    return this.characterState.get(characterId) || null;
  }

  /**
   * Save loaded Three.js model for character
   */
  setLoadedModel(characterId: string, model: THREE.Group | null): void {
    if (!this.availableCharacterIds.includes(characterId)) {
      console.error(`Invalid character ID: ${characterId}`);
      return;
    }
    this.loadedModels.set(characterId, model);
  }

  /**
   * Get loaded Three.js model for character
   */
  getLoadedModel(characterId: string): THREE.Group | null {
    return this.loadedModels.get(characterId) || null;
  }

  /**
   * Check if model is loaded
   */
  isModelLoaded(characterId: string): boolean {
    return this.loadedModels.get(characterId) !== null && this.loadedModels.get(characterId) !== undefined;
  }

  /**
   * Preserve visible state (for AI speaking state)
   */
  setCharacterVisibility(characterId: string, visible: boolean): void {
    this.updateCharacterState(characterId, { visible });
  }

  /**
   * Check if character should be visible
   */
  isCharacterVisible(characterId: string): boolean {
    const state = this.characterState.get(characterId);
    return state?.visible ?? false;
  }

  /**
   * Subscribe to character events
   */
  on(listener: CharacterEventListener): () => void {
    this.eventListeners.add(listener);
    return () => this.eventListeners.delete(listener);
  }

  /**
   * Emit event to all listeners
   */
  private emit(
    type: CharacterEventType,
    data: CharacterChangeEvent | CharacterProfile | ModelLoadError | CharacterState
  ): void {
    this.eventListeners.forEach((listener) => {
      try {
        listener(type, data);
      } catch (error) {
        console.error('Error in character event listener:', error);
      }
    });
  }

  /**
   * Report model load error
   */
  reportError(error: ModelLoadError): void {
    this.emit('character-error', error);
  }

  /**
   * Get character for fallback
   */
  getFallbackCharacterId(): string {
    return 'IRON_MAN'; // Always fall back to Iron Man
  }

  /**
   * Check if is transitioning
   */
  isTransitioningNow(): boolean {
    return this.isTransitioning;
  }

  /**
   * Reset to initial state
   */
  reset(): void {
    this.currentCharacterId = 'IRON_MAN';
    this.isTransitioning = false;
    this.characterState.clear();
    this.loadedModels.clear();
    this.eventListeners.clear();
  }
}

// Singleton instance
let instance: CharacterManager | null = null;

/**
 * Get or create singleton instance
 */
export function getCharacterManager(): CharacterManager {
  if (!instance) {
    instance = new CharacterManager();
  }
  return instance;
}
