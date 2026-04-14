import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'api_service.dart';

/// Résultat d'une tentative de login.
class AuthResult {
  final bool success;
  final String? error;
  final String? username;

  AuthResult({required this.success, this.error, this.username});
}

/// Service d'authentification.
/// Login via POST /login-app (form-encoded), session maintenue par cookies.
/// Le username est stocké dans flutter_secure_storage pour la reprise.
class AuthService {
  final _api = ApiService.instance;
  final _storage = const FlutterSecureStorage();

  static const _keyUsername = 'raya_username';

  /// Login : envoie username + password en form-encoded.
  /// Le backend répond avec un redirect 303 + cookie de session.
  Future<AuthResult> login(String username, String password) async {
    try {
      final response = await _api.postForm(
        '/login-app',
        data: {'username': username, 'password': password},
      );

      // Le backend renvoie 303 redirect vers /chat si OK
      // ou 401 avec HTML contenant <div class="error"> si KO
      if (response.statusCode == 303) {
        // Succès — le cookie de session est déjà stocké par dio_cookie_manager
        await _storage.write(key: _keyUsername, value: username);
        return AuthResult(success: true, username: username);
      }

      // Échec — extraire le message d'erreur du HTML
      final body = response.data?.toString() ?? '';
      String errorMsg = 'Identifiant ou mot de passe incorrect.';

      final errorMatch = RegExp(r'class="error">(.*?)</div>').firstMatch(body);
      if (errorMatch != null) {
        errorMsg = errorMatch.group(1) ?? errorMsg;
        // Nettoyer les entités HTML basiques
        errorMsg = errorMsg
            .replaceAll('&amp;', '&')
            .replaceAll('&lt;', '<')
            .replaceAll('&gt;', '>')
            .replaceAll('&#39;', "'")
            .replaceAll('&quot;', '"');
      }

      return AuthResult(success: false, error: errorMsg);
    } on DioException catch (e) {
      if (e.type == DioExceptionType.connectionTimeout) {
        return AuthResult(
          success: false,
          error: 'Impossible de joindre le serveur. Vérifie ta connexion.',
        );
      }
      return AuthResult(
        success: false,
        error: 'Erreur de connexion : ${e.message}',
      );
    } catch (e) {
      return AuthResult(success: false, error: 'Erreur inattendue : $e');
    }
  }

  /// Logout : appelle GET /logout et vide les cookies + storage.
  Future<void> logout() async {
    try {
      await _api.get('/logout');
    } catch (_) {}
    await _api.clearCookies();
    await _storage.delete(key: _keyUsername);
  }

  /// Vérifie si l'utilisateur a une session active.
  /// Teste en appelant GET /health (ou un endpoint authentifié).
  Future<bool> isLoggedIn() async {
    // D'abord vérifier si on a un cookie de session
    final hasSession = await _api.hasSession();
    if (!hasSession) return false;

    // Vérifier que la session est encore valide côté serveur
    try {
      final response = await _api.get('/token-status');
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// Récupère le username stocké localement.
  Future<String?> getSavedUsername() async {
    return await _storage.read(key: _keyUsername);
  }
}
