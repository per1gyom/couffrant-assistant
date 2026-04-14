import '../config/api_config.dart';
import 'api_service.dart';

/// Modele d'un message dans le chat
class ChatMessage {
  final String text;
  final bool isUser;
  final int? ariaMemoryId;
  final String? modelTier;
  final DateTime timestamp;

  ChatMessage({
    required this.text,
    required this.isUser,
    this.ariaMemoryId,
    this.modelTier,
    DateTime? timestamp,
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

  RayaResponse({
    required this.answer,
    required this.actions,
    required this.pendingActions,
    this.ariaMemoryId,
    this.modelTier,
    this.askChoice,
  });

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
}
