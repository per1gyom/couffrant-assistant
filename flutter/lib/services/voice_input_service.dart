import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import 'package:speech_to_text/speech_recognition_error.dart';
import 'package:speech_to_text/speech_recognition_result.dart';

/// Service de dictee vocale (Speech-To-Text).
/// Utilise le moteur natif iOS (SFSpeechRecognizer) via le package speech_to_text.
/// ON-DEVICE sur iOS 13+ : zero cloud, zero cout, excellent francais.
///
/// UX cible :
/// - Tap bouton micro -> start()
/// - Transcription partielle en direct (onPartial)
/// - Stop manuel (tap) OU auto apres silence prolonge (pauseFor)
/// - AUCUN envoi automatique : le texte final atterrit dans l'input,
///   l'utilisateur relit, corrige, puis envoie manuellement.
class VoiceInputService {
  static final VoiceInputService _instance = VoiceInputService._internal();
  factory VoiceInputService() => _instance;
  VoiceInputService._internal();

  final stt.SpeechToText _speech = stt.SpeechToText();
  bool _available = false;
  bool _isListening = false;
  String _currentText = '';

  bool get isListening => _isListening;
  bool get isAvailable => _available;
  String get currentText => _currentText;

  /// Initialise le moteur STT. A appeler une fois au demarrage de l'ecran
  /// (permissions demandees ici a la 1ere utilisation).
  Future<bool> init({
    void Function(String status)? onStatus,
    void Function(String error)? onError,
  }) async {
    if (_available) return true;
    try {
      _available = await _speech.initialize(
        onStatus: (s) {
          debugPrint('[VoiceInput] status: $s');
          if (s == 'done' || s == 'notListening') {
            _isListening = false;
          }
          onStatus?.call(s);
        },
        onError: (SpeechRecognitionError e) {
          debugPrint('[VoiceInput] error: ${e.errorMsg} (perm=${e.permanent})');
          _isListening = false;
          onError?.call(e.errorMsg);
        },
        debugLogging: false,
      );
    } catch (e) {
      debugPrint('[VoiceInput] init exception: $e');
      _available = false;
    }
    return _available;
  }

  /// Demarre l'ecoute.
  /// - [onPartial] : callback appele a chaque mise a jour de la transcription
  ///                 en cours (pour affichage live dans l'input)
  /// - [onFinal]   : callback appele quand l'ecoute se termine (manuel ou auto)
  ///                 avec le texte final consolide
  /// - [localeId]  : par defaut 'fr_FR', l'utilisateur parle francais
  /// - [pauseFor]  : duree de silence apres laquelle l'ecoute s'arrete auto
  /// - [listenFor] : duree maximale d'ecoute (garde-fou)
  ///
  /// Retourne true si l'ecoute a effectivement demarre.
  Future<bool> start({
    required void Function(String partial) onPartial,
    required void Function(String finalText) onFinal,
    String localeId = 'fr_FR',
    Duration pauseFor = const Duration(seconds: 2, milliseconds: 500),
    Duration listenFor = const Duration(minutes: 2),
  }) async {
    if (!_available) {
      final ok = await init();
      if (!ok) return false;
    }
    if (_isListening) return false;

    _currentText = '';
    _isListening = true;

    try {
      await _speech.listen(
        onResult: (SpeechRecognitionResult result) {
          _currentText = result.recognizedWords;
          if (result.finalResult) {
            onFinal(_currentText);
            _isListening = false;
          } else {
            onPartial(_currentText);
          }
        },
        localeId: localeId,
        listenFor: listenFor,
        pauseFor: pauseFor,
        listenOptions: stt.SpeechListenOptions(
          partialResults: true,
          cancelOnError: true,
          listenMode: stt.ListenMode.dictation,
        ),
      );
      return true;
    } catch (e) {
      debugPrint('[VoiceInput] start exception: $e');
      _isListening = false;
      return false;
    }
  }

  /// Arrete l'ecoute manuellement. Le callback onFinal sera appele avec le
  /// dernier texte consolide (meme comportement que l'arret auto).
  Future<void> stop() async {
    if (!_isListening) return;
    try {
      await _speech.stop();
    } catch (e) {
      debugPrint('[VoiceInput] stop exception: $e');
    }
    _isListening = false;
  }

  /// Annule l'ecoute sans declencher onFinal (utile si l'utilisateur rejette).
  Future<void> cancel() async {
    if (!_isListening) return;
    try {
      await _speech.cancel();
    } catch (e) {
      debugPrint('[VoiceInput] cancel exception: $e');
    }
    _isListening = false;
    _currentText = '';
  }
}
