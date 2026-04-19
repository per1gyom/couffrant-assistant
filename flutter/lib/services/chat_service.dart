import '../config/api_config.dart';
import 'api_service.dart';

/// Modele d'un message dans le chat
class ChatMessage {
  final String text;
  final bool isUser;
  final int? ariaMemoryId;
  final String? modelTier;
  final DateTime timestamp;
  // Message transitoire = erreur timeout affichee en attendant la reponse
  // fantome recuperee par polling /chat/history
  final bool isTransient;

  ChatMessage({
    required this.text,
    required this.isUser,
    this.ariaMemoryId,
    this.modelTier,
    DateTime? timestamp,
    this.isTransient = false,
  }) : timestamp = timestamp ?? DateTime.now();
}

/// Donnees de choix interactif (ask_choice)
class AskChoice {
  final String question;
  final List<String> options;

  AskChoice({required this.question, required this.options});

  factory AskChoice.fromJson(Map<String, dynamic> json) {
    return AskChoice(
      question: json['question'] ?? '',
      options: List<String>.from(json['options'] ?? []),
    );
  }
}

/// Action en attente de confirmation
class PendingAction {
  final int id;
  final String actionType;
  final String label;
  final Map<String, dynamic> payload;

  PendingAction({
    required this.id,
    required this.actionType,
    required this.label,
    required this.payload,
  });

  factory PendingAction.fromJson(Map<String, dynamic> json) {
    return PendingAction(
      id: json['id'] ?? 0,
      actionType: json['action_type'] ?? '',
      label: json['label'] ?? 'Action #${json['id']}',
      payload: Map<String, dynamic>.from(json['payload'] ?? {}),
    );
  }
}

/// Reponse complete de /raya
class RayaResponse {
  final String answer;
  final List<String> actions;
  final List<PendingAction> pendingActions;
  final int? ariaMemoryId;
  final String? modelTier;
  final AskChoice? askChoice;
  // Timeout "fantome" : le backend a renvoye un timeout mais le thread Python
  // continue en arriere-plan. Le client doit poller /chat/history.
  final bool isError;
  final String? errorType;

  RayaResponse({
    required this.answer,
    required this.actions,
    required this.pendingActions,
    this.ariaMemoryId,
    this.modelTier,
    this.askChoice,
    this.isError = false,
    this.errorType,
  });

  bool get isGhostTimeout => isError && errorType == 'timeout';

  factory RayaResponse.fromJson(Map<String, dynamic> json) {
    return RayaResponse(
      answer: json['answer'] ?? '',
      actions: List<String>.from(json['actions'] ?? []),
      pendingActions: (json['pending_actions'] as List<dynamic>?)
              ?.map((e) => PendingAction.fromJson(e))
              .toList() ??
          [],
      ariaMemoryId: json['aria_memory_id'],
      modelTier: json['model_tier'],
      askChoice: json['ask_choice'] != null
          ? AskChoice.fromJson(json['ask_choice'])
          : null,
      isError: json['is_error'] == true,
      errorType: json['error_type'] as String?,
    );
  }
}

/// Service de chat — communique avec POST /raya et GET /chat/history
class ChatService {
  final ApiService _api = ApiService.instance;

  /// Envoie un message a Raya
  Future<RayaResponse> sendMessage(
    String query, {
    String? fileData,
    String? fileType,
    String? fileName,
  }) async {
    final body = <String, dynamic>{'query': query};
    if (fileData != null) body['file_data'] = fileData;
    if (fileType != null) body['file_type'] = fileType;
    if (fileName != null) body['file_name'] = fileName;

    final response = await _api.postJson(ApiConfig.rayaEndpoint, body);

    if (response.statusCode == 200 && response.data is Map<String, dynamic>) {
      return RayaResponse.fromJson(response.data);
    }

    throw Exception('Erreur Raya (${response.statusCode})');
  }

  /// Charge l'historique recent
  Future<List<ChatMessage>> loadHistory({int limit = 20}) async {
    final response = await _api.get(
      ApiConfig.historyEndpoint,
      params: {'limit': limit},
    );

    if (response.statusCode == 200 && response.data is List) {
      final messages = <ChatMessage>[];
      for (final item in response.data) {
        if (item['user'] != null) {
          messages.add(ChatMessage(
            text: item['user'],
            isUser: true,
          ));
        }
        if (item['raya'] != null) {
          messages.add(ChatMessage(
            text: item['raya'],
            isUser: false,
            ariaMemoryId: item['id'],
          ));
        }
      }
      return messages;
    }
    return [];
  }

  /// Polling fantôme : quand /raya a renvoyé un timeout mais que le thread
  /// Python a continué à s'executer en arriere-plan. On verifie /chat/history
  /// toutes les 3s pendant 90s (30 tentatives) pour recuperer la vraie reponse.
  ///
  /// [userText] : le texte envoye par l'user (pour matcher l'entree historique)
  /// [sentAt]   : timestamp d'envoi (tolerance 15s avant pour latence reseau)
  ///
  /// Retourne la reponse Raya si trouvee, null sinon.
  Future<GhostMatch?> pollForGhostResponse({
    required String userText,
    required DateTime sentAt,
    int maxAttempts = 30,
    Duration interval = const Duration(seconds: 3),
  }) async {
    final userTextNorm = userText.trim();
    final userKey = userTextNorm.length > 200
        ? userTextNorm.substring(0, 200)
        : userTextNorm;
    // Tolerance de 15s avant l'envoi pour absorber l'horloge serveur
    final minTs = sentAt.subtract(const Duration(seconds: 15));

    for (int i = 0; i < maxAttempts; i++) {
      await Future.delayed(interval);
      try {
        final r = await _api.get(
          ApiConfig.historyEndpoint,
          params: {'limit': 3},
        );
        if (r.statusCode != 200 || r.data is! List) continue;
        for (final item in r.data) {
          if (item is! Map) continue;
          final itemUser = (item['user'] as String?)?.trim() ?? '';
          final itemRaya = item['raya'] as String?;
          if (itemRaya == null || itemRaya.isEmpty) continue;
          final itemUserKey = itemUser.length > 200
              ? itemUser.substring(0, 200)
              : itemUser;
          if (itemUserKey != userKey) continue;
          // Parse timestamp serveur (format ISO ou timestamp)
          DateTime? itemTs;
          final tsRaw = item['created_at'] ?? item['ts'];
          if (tsRaw is String) {
            try { itemTs = DateTime.parse(tsRaw); } catch (_) {}
          }
          if (itemTs == null || itemTs.isBefore(minTs)) continue;
          // Match trouve
          return GhostMatch(
            answer: itemRaya,
            ariaMemoryId: item['id'] is int ? item['id'] as int : null,
          );
        }
      } catch (_) {
        // ignore, on retente
      }
    }
    return null;
  }
}

/// Resultat du polling fantome
class GhostMatch {
  final String answer;
  final int? ariaMemoryId;
  GhostMatch({required this.answer, this.ariaMemoryId});
}
