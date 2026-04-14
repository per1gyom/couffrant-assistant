import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../config/api_config.dart';
import 'api_service.dart';

/// Résultat d'une tentative de login
class AuthResult {
  final bool success;
  final String? error;

  AuthResult({required this.success, this.error});
}

/// Service d'authentification.
/// Le backend utilise des sessions cookies.
/// Le login POST /login-app retourne une redirection 303 vers /chat si OK,
/// ou un 401 avec le HTML de la page login si KO.
class AuthService {
  final ApiService _api = ApiService.instance;
  final FlutterSecureStorage _storage = const FlutterSecureStorage();

  static const _keyUsername = 'raya_username';
  static const _keyLoggedIn = 'raya_logged_in';

  /// Login avec username + password
  Future<AuthResult> login(String username, String password) async {
    try {
      final response = await _api.postForm(
        ApiConfig.loginEndpoint,
        {'username': username, 'password': password},
      );

      // Le backend redirige vers /chat (303) en cas de succès
      // ou vers /forced-reset (303) si reset de mot de passe requis
      if (response.statusCode == 303 || response.statusCode == 302) {
        final location = response.headers['location']?.first ?? '';
        if (location.contains('/chat') || location.contains('/forced-reset')) {
          // Succès — sauvegarder le username localement
          await _storage.write(key: _keyUsername, value: username);
          await _storage.write(key: _keyLoggedIn, value: 'true');
          return AuthResult(success: true);
        }
      }

      // 401 = identifiants incorrects
      if (response.statusCode == 401) {
        return AuthResult(
          success: false,
          error: 'Identifiant ou mot de passe incorrect.',
        );
      }

      return AuthResult(
        success: false,
        error: 'Erreur de connexion (${response.statusCode}).',
      );
    } catch (e) {
      return AuthResult(
        success: false,
        error: 'Impossible de joindre le serveur Raya.',
      );
    }
  }

  /// Déconnexion
  Future<void> logout() async {
    try {
      await _api.get(ApiConfig.logoutEndpoint);
    } catch (_) {}
    await _api.clearCookies();
    await _storage.delete(key: _keyUsername);
    await _storage.delete(key: _keyLoggedIn);
  }

  /// Vérifie si l'utilisateur est connecté (session valide)
  Future<bool> isLoggedIn() async {
    // D'abord vérifier le stockage local
    final loggedIn = await _storage.read(key: _keyLoggedIn);
    if (loggedIn != 'true') return false;

    // Ensuite vérifier que la session est encore valide côté serveur
    try {
      final response = await _api.get(ApiConfig.healthEndpoint);
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// Récupère le username stocké
  Future<String?> getUsername() async {
    return await _storage.read(key: _keyUsername);
  }
}
