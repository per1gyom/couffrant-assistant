import '../config/api_config.dart';
import 'api_service.dart';

class AuthResult {
  final bool success;
  final String? error;
  AuthResult({required this.success, this.error});
}

class AuthService {
  final ApiService _api = ApiService.instance;
  static String? _cachedUsername;
  static bool _isLoggedIn = false;

  Future<AuthResult> login(String username, String password) async {
    try {
      final response = await _api.postForm(
        ApiConfig.loginEndpoint,
        {'username': username, 'password': password},
      );
      if (response.statusCode == 303 || response.statusCode == 302) {
        final location = response.headers['location']?.first ?? '';
        if (location.contains('/chat') || location.contains('/forced-reset')) {
          _cachedUsername = username;
          _isLoggedIn = true;
          return AuthResult(success: true);
        }
      }
      if (response.statusCode == 401) {
        return AuthResult(success: false, error: 'Identifiant ou mot de passe incorrect.');
      }
      return AuthResult(success: false, error: 'Erreur (${response.statusCode}).');
    } catch (e) {
      return AuthResult(success: false, error: 'Impossible de joindre Raya.');
    }
  }

  Future<void> logout() async {
    try { await _api.get(ApiConfig.logoutEndpoint); } catch (_) {}
    await _api.clearCookies();
    _cachedUsername = null;
    _isLoggedIn = false;
  }

  Future<bool> isLoggedIn() async {
    if (!_isLoggedIn) return false;
    try {
      final r = await _api.get(ApiConfig.healthEndpoint);
      return r.statusCode == 200;
    } catch (_) { return false; }
  }

  String? getUsername() => _cachedUsername;
}
