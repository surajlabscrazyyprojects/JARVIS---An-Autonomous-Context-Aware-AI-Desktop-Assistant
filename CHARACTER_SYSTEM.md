# Multi-Character Mode System - Complete Implementation Guide

## Overview

This document describes the complete production-grade multi-character mode system for the JARVIS HUD application. The system enables seamless character switching between JARVIS, Spider-Man, Hulk, and Batman with full voice profile integration and extensible architecture.

## Architecture

### Core Components

#### 1. **Character Type System** (`src/types/Character.ts`)
- **Purpose**: Defines all TypeScript interfaces for type safety
- **Key Types**:
  - `CharacterProfile`: Complete character configuration
  - `CharacterVoiceProfile`: Voice-specific settings with emotion ranges
  - `CharacterModel`: 3D model configuration
  - `CharacterState`: Runtime state (scale, rotation, visibility)
  - `CharacterChangeEvent`: Event fired when character switches

#### 2. **Character Registry** (`src/config/characters.ts`)
- **Purpose**: Centralized configuration for all characters
- **Contains**: 4 pre-configured character profiles (JARVIS, Spider-Man, Hulk, Batman)
- **Extensibility**: Add new characters by adding a single profile object
- **Voice IDs**: Each character has a Fish Audio reference ID
- **System Prompts**: Future AI personality configuration for each character

#### 3. **Character Manager** (`src/character/CharacterManager.ts`)
- **Purpose**: Single source of truth for character state
- **Responsibilities**:
  - Track current active character
  - Manage character switching with validation
  - Preserve per-character state (scale, rotation)
  - Emit events for character changes
  - Track loaded 3D models

**Key Methods**:
```typescript
switchCharacter(characterId, reason)     // Switch to new character
getCharacterState(characterId)           // Get scale/rotation state
getCurrentCharacterProfile()             // Get active character config
on(listener)                             // Subscribe to events
```

#### 4. **Voice Profile Manager** (`src/voice/VoiceProfileManager.ts`)
- **Purpose**: Dynamic voice configuration without hardcoding
- **Capabilities**:
  - Emotion detection from text
  - Speed adjustment based on character personality
  - Fish Audio request building
  - Multiple voice profiles per character (future)

**Key Methods**:
```typescript
setActiveProfile(profile)                // Set character voice
detectEmotion(text)                      // Get emotion speed modifier
buildTTSRequestBody(text)                // Build Fish Audio request
```

#### 5. **Model Loader** (`src/models/ModelLoader.ts`)
- **Purpose**: Handle glTF model loading with proper resource cleanup
- **Features**:
  - Model caching to prevent duplicate loads
  - Material override system
  - Automatic model centering
  - Complete disposal to prevent VRAM leaks
  - Promise-based loading with progress tracking

**Key Methods**:
```typescript
loadModel(profile, options)              // Load character model
disposeModel(model)                      // Clean up resources
clearCache()                             // Clear all cached models
```

#### 6. **Character Integration** (`src/character/CharacterIntegration.ts`)
- **Purpose**: Bridge character system with Three.js scene
- **Responsibilities**:
  - Initialize character system with scene
  - Handle model switching animations
  - Fade transitions (300-500ms)
  - UI updates and theme switching
  - Error handling with fallback

## Character Profiles

### JARVIS (Iron Man AI)
- **Model**: `./scene.gltf`
- **Voice**: Reference ID `269ac1ab2f934360a47f5a6eb51c18cb`
- **Color**: Cyan (#00d4ff)
- **Personality**: British precision, dry wit, calculated
- **Accent**: British
- **Default Speed**: 0.92

### Spider-Man (Miles Morales)
- **Model**: `./miles_morales/scene.gltf`
- **Voice**: Reference ID `6fc8480c052b4914b565ef1dd350bed5`
- **Color**: Orange (#ff6600)
- **Personality**: Energetic, street-smart, quick-witted
- **Accent**: Brooklyn
- **Default Speed**: 1.05

### Hulk (Bruce Banner)
- **Model**: `./hulk_infinity_hulk/scene.gltf`
- **Voice**: To be configured
- **Color**: Green (#00ff00)
- **Personality**: Powerful, direct, surprisingly thoughtful
- **Accent**: Deep
- **Default Speed**: 0.85

### Batman (Bruce Wayne)
- **Model**: `./batman_armoredtexturedrigged/scene.gltf`
- **Voice**: To be configured
- **Color**: Yellow (#ffff00)
- **Personality**: Strategic, mysterious, always prepared
- **Accent**: Gotham
- **Default Speed**: 0.88

## Integration with Existing Code

### HTML Navigation
Replace the old navigation:
```html
<!-- OLD -->
<div class="hud-tab">System</div>
<div class="hud-tab">Armor</div>

<!-- NEW -->
<div class="hud-tab active character-nav-btn" data-character="JARVIS">JARVIS</div>
<div class="hud-tab character-nav-btn" data-character="SPIDER_MAN">SPIDER-MAN</div>
<div class="hud-tab character-nav-btn" data-character="HULK">HULK</div>
<div class="hud-tab character-nav-btn" data-character="BATMAN">BATMAN</div>
```

### Voice Profile Integration
The `speakWithFishAudio()` function now dynamically reads from current character:

```javascript
async function speakWithFishAudio(text) {
  let referenceId = FISH_VOICE_ID; // Default
  let speechSpeed = 0.92;
  
  if (window.__characterManager) {
    const voiceManager = window.__voiceProfileManager;
    const config = voiceManager.buildTTSConfig(text);
    referenceId = config.referenceId;
    speechSpeed = config.prosody.speed;
  }
  
  // Use referenceId in Fish Audio request
}
```

### Character Switching
Characters can be switched via:
1. **UI Button Click**: User clicks character name in navigation
2. **Voice Command**: Speech recognition detects character name
3. **System**: Programmatic switch

## Usage Examples

### Switch Character Programmatically
```javascript
const charMgr = window.__characterManager;
await charMgr.switchCharacter('SPIDER_MAN', 'system');
```

### Listen to Character Changes
```javascript
const charMgr = getCharacterManager();
charMgr.on((type, data) => {
  if (type === 'character-change') {
    console.log(`Switched from ${data.previousCharacterId} to ${data.newCharacterId}`);
  }
});
```

### Get Current Character Voice
```javascript
const voiceMgr = window.__voiceProfileManager;
const config = voiceMgr.buildTTSConfig("Hello, sir");
// config.referenceId contains current character's voice ID
// config.prosody.speed contains emotion-adjusted speed
```

## Performance Considerations

### Memory Management
- **Model Caching**: Loaded models are cached to prevent reloads
- **One Model Active**: Only one character model in memory at a time
- **Proper Disposal**: All geometries, materials, textures are disposed
- **No VRAM Leaks**: Complete cleanup of WebGL resources

### Transition Performance
- **Smooth Fades**: 300-500ms fade transitions
- **No Renderer Reset**: Scene/camera/lighting preserved
- **Minimal State Changes**: Only swap active model

### Voice Profile
- **Lightweight**: No additional HTTP requests (voice ID stored in registry)
- **Dynamic**: Speech speed adjusts per emotion
- **Fallback**: Graceful degradation if character system unavailable

## Extensibility

### Adding a New Character

1. **Update Character Registry** (`src/config/characters.ts`):
```typescript
export const CHARACTER_REGISTRY: Record<string, CharacterProfile> = {
  NEW_CHARACTER: {
    id: 'NEW_CHARACTER',
    displayName: 'New Character',
    model: {
      id: 'new-model',
      path: './path/to/model.gltf',
      scale: 1,
      defaultPosition: { x: 0, y: 0, z: 0 },
      defaultRotation: { x: 0, y: 0, z: 0 },
      materialOverride: {
        color: 0xaabbcc,
        emissive: 0xddeeff,
        emissiveIntensity: 0.5,
        opacity: 0.9,
      },
    },
    voiceProfile: {
      id: 'new-voice',
      referenceId: 'fish-audio-id-here',
      name: 'Character Name',
      accent: 'Accent Description',
      speed: 0.95,
      emotionalRange: {
        excited: { speed: 1.1 },
        calm: { speed: 0.85 },
      },
    },
    animationSet: {
      idle: null,
      speaking: null,
      thinking: null,
    },
    handTrackingEnabled: true,
    description: 'Character description',
    color: '#aabbcc',
  },
};
```

2. **Add Navigation Button** in HTML:
```html
<div class="hud-tab character-nav-btn" data-character="NEW_CHARACTER">New Character</div>
```

3. **No Code Changes Required**: The system is fully configuration-driven!

### Future Extensibility Fields
Each character profile includes reserved fields for future features:
```typescript
systemPrompt?: string;           // Custom AI behavior
memoryStyle?: string;            // Memory processing style
emotionStyle?: string;           // Emotion handling
animationStyle?: string;         // Animation preferences
gestureStyle?: string;           // Hand gesture preferences
colorTheme?: string;             // UI color scheme
particleTheme?: string;          // Particle effect theme
cameraPreset?: string;           // Camera positioning
speechPreset?: string;           // Speech characteristics
```

## Error Handling

### Model Load Failures
- Shows HUD notification
- Falls back to JARVIS (default character)
- Prevents empty scene
- Logs error for debugging

### Voice Profile Issues
- Falls back to browser Web Speech API
- Uses default voice settings
- Continues gracefully

### Character Switch Errors
- Reports error to CharacterManager
- Maintains current character
- User can retry

## Testing Checklist

- [ ] JARVIS loads with correct cyan glow
- [ ] Spider-Man switches with orange accent
- [ ] Hulk switches with green glow
- [ ] Batman switches with yellow accent
- [ ] Voice changes when switching characters
- [ ] All previous models disposed (check console)
- [ ] Hand tracking works on all characters
- [ ] Camera, lighting, controls preserved during switch
- [ ] HUD state maintained during transitions
- [ ] Speech recognition detects character names
- [ ] Fade transitions smooth (no white flashes)
- [ ] No memory leaks (Task Manager GPU usage stable)
- [ ] WebSocket connection preserved
- [ ] Conversation history maintained

## Performance Metrics

**Target Performance**:
- Model load time: < 2 seconds
- Character switch time: < 1 second
- Fade transition: 300-500ms
- Memory per character: < 50MB
- VRAM per character: < 100MB
- FPS during transition: 30+

## File Structure

```
iron-man-with-no-rig/
├── src/
│   ├── character/
│   │   ├── CharacterManager.ts
│   │   └── CharacterIntegration.ts
│   ├── config/
│   │   └── characters.ts
│   ├── models/
│   │   └── ModelLoader.ts
│   ├── types/
│   │   └── Character.ts
│   └── voice/
│       └── VoiceProfileManager.ts
├── hologram_environment.html
├── INTEGRATION_GUIDE.md
└── CHARACTER_SYSTEM.md (this file)
```

## Troubleshooting

### Character won't switch
- Check browser console for errors
- Verify character ID matches exactly
- Check if model path is correct

### Voice not changing
- Verify `window.__voiceProfileManager` exists
- Check Fish API key is valid
- Confirm character voice reference ID is set

### Models not loading
- Check browser DevTools Network tab
- Verify glTF file paths are correct
- Check for CORS issues

### Memory leaks
- Force garbage collection (DevTools)
- Check WebGL context isn't growing
- Verify dispose methods are called

## API Key Management

**Current Configuration**:
- Fish Audio API key: configure `FISH_API_KEY` (or `FISH_AUDIO_API_KEY`) in the local environment; never commit the value.
- Groq API Key: set `GROQ_API_KEY` in the local environment

**Security Note**: In production, move these to environment variables or backend.

## License

This multi-character system is part of the JARVIS Agent project and follows the same licensing as the parent project.

## Support

For issues or feature requests, refer to the main JARVIS project documentation.
