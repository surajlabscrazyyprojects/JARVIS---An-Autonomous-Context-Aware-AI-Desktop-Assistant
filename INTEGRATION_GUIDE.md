/**
 * INTEGRATION PATCH for hologram_environment.html
 * 
 * This file contains the code changes needed to integrate the character system.
 * Add this to your main module script after the existing setup.
 * 
 * LOCATION IN EXISTING FILE: After the "loader.load('./scene.gltf'...)" section
 * and before the "Hand Tracking Variables" section.
 */

// ===== CHARACTER SYSTEM INITIALIZATION =====
// Import character system modules (these will be added as modules in the HTML)
import { getCharacterManager } from './src/character/CharacterManager.js';
import { getVoiceProfileManager } from './src/voice/VoiceProfileManager.js';
import { 
  initializeCharacterSystem, 
  switchToCharacter,
  buildTTSRequest,
  updateCharacterVisibility 
} from './src/character/CharacterIntegration.js';
import { CHARACTER_REGISTRY } from './src/config/characters.js';

// Initialize character system with Three.js scene
initializeCharacterSystem(scene, pivot, loader);

// Load initial JARVIS model (replace existing iron man load)
(async () => {
  try {
    await switchToCharacter('JARVIS', 'system');
  } catch (error) {
    console.error('Failed to initialize JARVIS:', error);
  }
})();

// Store reference for voice updates
const characterManager = getCharacterManager();
const voiceProfileManager = getVoiceProfileManager();

// ===== MODIFY EXISTING VOICE FUNCTION =====
// Replace the existing speakWithFishAudio function with this updated version:

async function speakWithFishAudio(text) {
  // Use character's voice profile instead of hardcoded FISH_VOICE_ID
  const voiceConfig = buildTTSRequest(text);
  
  try {
    const response = await fetch('https://api.fish.audio/v1/tts', {
      method: 'POST',
      headers: { 
        'Authorization': `Bearer ${FISH_API_KEY}`, 
        'Content-Type': 'application/json' 
      },
      body: JSON.stringify(voiceConfig)
    });

    if (!response.ok) throw new Error(`Fish Audio error: ${response.status}`);
    const audioBlob = await response.blob();
    const audioUrl = URL.createObjectURL(audioBlob);

    jarvisAudioElement.src = audioUrl;
    setAppState('AI_SPEAKING');
    
    // Update character visibility for voice state
    updateCharacterVisibility('AI_SPEAKING');
    
    showSubtitles(text);
    
    if (aiAudioCtx && aiAudioCtx.state === 'suspended') await aiAudioCtx.resume();
    
    jarvisAudioElement.play();
    
    jarvisAudioElement.onended = () => {
      setAppState('IDLE');
      updateCharacterVisibility('IDLE');
      hideSubtitles();
      URL.revokeObjectURL(audioUrl);
    };
  } catch (err) {
    console.error('TTS failed:', err);
    fallbackBrowserTTS(text);
  }
}

// ===== MODIFY SPEECH RECOGNITION FOR CHARACTER SWITCHING =====
// Add this to the continuousRecognition.onresult callback (around line 2500):

// After the existing wake word and arc reactor detection, add character detection:

// Detect character switching by voice command
const JARVIS_VARIANTS = ['jarvis', 'j.a.r.v.i.s', 'jarvis ai', 'hey jarvis'];
const SPIDER_MAN_VARIANTS = ['spider man', 'spiderman', 'miles', 'miles morales', 'web head'];
const HULK_VARIANTS = ['hulk', 'bruce', 'bruce banner', 'smash', 'green giant'];
const BATMAN_VARIANTS = ['batman', 'dark knight', 'bruce wayne', 'gotham'];

const hearsJarvis = fuzzyContains(fullTranscript, JARVIS_VARIANTS, 2);
const hearsSpiderMan = fuzzyContains(fullTranscript, SPIDER_MAN_VARIANTS, 2);
const hearsHulk = fuzzyContains(fullTranscript, HULK_VARIANTS, 2);
const hearsBatman = fuzzyContains(fullTranscript, BATMAN_VARIANTS, 2);

// Character switching (takes priority over model switching)
if (hearsSpiderMan && characterManager.getCurrentCharacterId() !== 'SPIDER_MAN') {
  await switchToCharacter('SPIDER_MAN', 'voice-command');
} else if (hearsHulk && characterManager.getCurrentCharacterId() !== 'HULK') {
  await switchToCharacter('HULK', 'voice-command');
} else if (hearsBatman && characterManager.getCurrentCharacterId() !== 'BATMAN') {
  await switchToCharacter('BATMAN', 'voice-command');
} else if (hearsJarvis && characterManager.getCurrentCharacterId() !== 'JARVIS') {
  await switchToCharacter('JARVIS', 'voice-command');
}

// Update UI when app state changes
const _origSetAppState = setAppState;
window.setAppState = function(s) {
  _origSetAppState(s);
  updateCharacterVisibility(s);
};
