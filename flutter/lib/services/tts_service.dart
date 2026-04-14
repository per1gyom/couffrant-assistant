import 'dart:typed_data';
import 'package:dio/dio.dart';
import 'package:just_audio/just_audio.dart';
import '../config/api_config.dart';
import 'api_service.dart';

/// Service TTS — appelle POST /speak et lit l'audio via just_audio.
/// Resout le probleme #1 de la PWA : autoplay bloque sur iOS Safari.
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

      final response = await _api.dio.post(
        ApiConfig.speakEndpoint,
        data: {'text': clean, 'speed': speed},
        options: Options(
          responseType: ResponseType.bytes,
          receiveTimeout: const Duration(seconds: 30),
        ),
      );

      if (response.statusCode == 200 && response.data != null) {
        final bytes = Uint8List.fromList(response.data as List<int>);
        await _player.setAudioSource(BytesAudioSource(bytes));
        await _player.play();
        await _player.processingStateStream.firstWhere(
          (state) => state == ProcessingState.completed,
        );
      }
    } catch (_) {
    } finally {
      _isSpeaking = false;
    }
  }

  /// Arrete la lecture en cours
  Future<void> stop() async {
    _isSpeaking = false;
    await _player.stop();
  }

  void dispose() {
    _player.dispose();
  }
}

/// Source audio depuis des bytes en memoire
class BytesAudioSource extends StreamAudioSource {
  final Uint8List _bytes;

  BytesAudioSource(this._bytes);

  @override
  Future<StreamAudioResponse> request([int? start, int? end]) async {
    final s = start ?? 0;
    final e = end ?? _bytes.length;
    return StreamAudioResponse(
      sourceLength: _bytes.length,
      contentLength: e - s,
      offset: s,
      stream: Stream.value(_bytes.sublist(s, e)),
      contentType: 'audio/mpeg',
    );
  }
}
