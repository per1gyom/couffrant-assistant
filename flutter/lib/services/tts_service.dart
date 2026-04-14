import 'dart:typed_data';
import 'package:just_audio/just_audio.dart';
import '../config/api_config.dart';
import 'api_service.dart';

/// Service TTS — appelle POST /speak et lit l'audio via just_audio.
/// Résout le problème #1 de la PWA : autoplay bloqué sur iOS Safari.
/// En natif Flutter, just_audio lit sans restriction.
class TtsService {
  final ApiService _api = ApiService.instance;
  final AudioPlayer _player = AudioPlayer();
  bool _isSpeaking = false;
  double speed = 1.2;

  bool get isSpeaking => _isSpeaking;

  /// Lit un texte via ElevenLabs TTS
  Future<void> speak(String text) async {
    if (text.isEmpty) return;

    // Nettoyer le markdown avant envoi
    var clean = text;
    clean = clean.replaceAll(RegExp(r'#{1,6}\s+'), '');
    clean = clean.replaceAll(RegExp(r'\*\*(.*?)\*\*'), r'$1');
    clean = clean.replaceAll(RegExp(r'\*(.*?)\*'), r'$1');
    clean = clean.replaceAll(RegExp(r'`(.*?)`'), r'$1');
    clean = clean.replaceAll(RegExp(r'---+'), '');
    clean = clean.replaceAll(RegExp(r'\|.*?\|'), '');
    clean = clean.replaceAll(RegExp(r'\[([^\]]+)\]\([^\)]+\)'), r'$1');
    clean = clean.trim();
    if (clean.length > 2500) clean = clean.substring(0, 2500);
    if (clean.isEmpty) return;

    try {
      _isSpeaking = true;

      // Appel POST /speak — retourne audio/mpeg
      final response = await _api.dio.post(
        ApiConfig.speakEndpoint,
        data: {'text': clean, 'speed': speed},
        options: _api.dio.options.copyWith(
          responseType: ResponseType.bytes,
          receiveTimeout: const Duration(seconds: 30),
        ).toOptions(),
      );

      if (response.statusCode == 200 && response.data != null) {
        // Lire les bytes audio directement
        final bytes = Uint8List.fromList(response.data as List<int>);

        // Charger et lire avec just_audio (autoplay natif — pas de restriction iOS)
        await _player.setAudioSource(
          _BytesAudioSource(bytes, 'audio/mpeg'),
        );
        await _player.play();

        // Attendre la fin de la lecture
        await _player.processingStateStream.firstWhere(
          (state) => state == ProcessingState.completed,
        );
      }
    } catch (e) {
      // Silence en cas d'erreur TTS — pas critique
    } finally {
      _isSpeaking = false;
    }
  }

  /// Arrête la lecture en cours
  Future<void> stop() async {
    _isSpeaking = false;
    await _player.stop();
  }

  /// Libère les ressources
  void dispose() {
    _player.dispose();
  }
}

/// Options Dio en tant que Options (pas BaseOptions)
extension on BaseOptions {
  Options toOptions() {
    return Options(
      receiveTimeout: receiveTimeout,
      responseType: responseType,
      headers: headers,
    );
  }
}

/// Source audio depuis des bytes en mémoire
class _BytesAudioSource extends StreamAudioSource {
  final Uint8List _bytes;
  final String _contentType;

  _BytesAudioSource(this._bytes, this._contentType);

  @override
  Future<StreamAudioResponse> request([int? start, int? end]) async {
    final effectiveStart = start ?? 0;
    final effectiveEnd = end ?? _bytes.length;
    return StreamAudioResponse(
      sourceLength: _bytes.length,
      contentLength: effectiveEnd - effectiveStart,
      offset: effectiveStart,
      stream: Stream.value(
        _bytes.sublist(effectiveStart, effectiveEnd),
      ),
      contentType: _contentType,
    );
  }
}
