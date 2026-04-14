import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import '../config/api_config.dart';
import 'api_service.dart';

/// Service feedback — gère 👍👎💡🐛
class FeedbackService {
  final ApiService _api = ApiService.instance;

  /// Envoie un feedback positif 👍
  Future<bool> sendPositive(int ariaMemoryId) async {
    try {
      final r = await _api.postJson(ApiConfig.feedbackEndpoint, {
        'aria_memory_id': ariaMemoryId,
        'feedback_type': 'positive',
      });
      return r.statusCode == 200;
    } catch (_) { return false; }
  }

  /// Envoie un feedback negatif 👎 avec commentaire
  Future<bool> sendNegative(int ariaMemoryId, {String comment = ''}) async {
    try {
      final r = await _api.postJson(ApiConfig.feedbackEndpoint, {
        'aria_memory_id': ariaMemoryId,
        'feedback_type': 'negative',
        'comment': comment,
      });
      return r.statusCode == 200;
    } catch (_) { return false; }
  }

  /// Recupere le "pourquoi" d'une reponse 💡
  Future<Map<String, dynamic>?> getWhy(int ariaMemoryId) async {
    try {
      final r = await _api.get('${ApiConfig.whyEndpoint}/$ariaMemoryId');
      if (r.statusCode == 200 && r.data is Map<String, dynamic>) {
        return r.data;
      }
    } catch (_) {}
    return null;
  }

  /// Envoie un bug report 🐛
  Future<int?> sendBugReport({
    required String reportType,
    required String description,
    int? ariaMemoryId,
    String? userInput,
    String? rayaResponse,
  }) async {
    try {
      final deviceInfo = await _getDeviceInfo();
      final r = await _api.postJson(ApiConfig.bugReportEndpoint, {
        'report_type': reportType,
        'description': description,
        if (ariaMemoryId != null) 'aria_memory_id': ariaMemoryId,
        if (userInput != null) 'user_input': userInput.length > 500
            ? userInput.substring(0, 500) : userInput,
        if (rayaResponse != null) 'raya_response': rayaResponse.length > 2000
            ? rayaResponse.substring(0, 2000) : rayaResponse,
        'device_info': deviceInfo,
      });
      if (r.statusCode == 200 && r.data is Map) {
        return r.data['id'];
      }
    } catch (_) {}
    return null;
  }

  /// Recupere les infos de l'appareil
  Future<String> _getDeviceInfo() async {
    try {
      final plugin = DeviceInfoPlugin();
      if (kIsWeb) {
        final info = await plugin.webBrowserInfo;
        return '${info.browserName.name} [web]';
      }
      final info = await plugin.iosInfo;
      return '${info.name} ${info.systemName} ${info.systemVersion} [mobile]';
    } catch (_) {
      return 'unknown [mobile]';
    }
  }
}
