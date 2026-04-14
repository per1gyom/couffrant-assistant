import 'package:dio/dio.dart';
import 'package:cookie_jar/cookie_jar.dart';
import 'package:dio_cookie_manager/dio_cookie_manager.dart';
import 'package:path_provider/path_provider.dart';
import '../config/api_config.dart';

/// Client HTTP singleton avec gestion automatique des cookies de session.
/// Reproduit le comportement du navigateur pour la PWA :
/// le backend utilise des cookies de session (pas de JWT).
class ApiService {
  static ApiService? _instance;
  late final Dio dio;
  late final PersistCookieJar _cookieJar;
  bool _initialized = false;

  ApiService._();

  static ApiService get instance {
    _instance ??= ApiService._();
    return _instance!;
  }

  /// Initialiser dio + cookie jar persistant.
  /// Appeler une seule fois au démarrage de l'app.
  Future<void> init() async {
    if (_initialized) return;

    final dir = await getApplicationDocumentsDirectory();
    _cookieJar = PersistCookieJar(
      storage: FileStorage('${dir.path}/.cookies/'),
    );

    dio = Dio(BaseOptions(
      baseUrl: ApiConfig.baseUrl,
      connectTimeout: Duration(seconds: ApiConfig.connectTimeout),
      receiveTimeout: Duration(seconds: ApiConfig.receiveTimeout),
      // Important : suivre les redirections mais ne pas changer la méthode
      followRedirects: false,
      validateStatus: (status) => status != null && status < 500,
      headers: {
        'Accept': 'application/json',
      },
    ));

    dio.interceptors.add(CookieManager(_cookieJar));

    _initialized = true;
  }

  /// Vider les cookies (logout).
  Future<void> clearCookies() async {
    await _cookieJar.deleteAll();
  }

  /// Vérifier si on a un cookie de session valide.
  Future<bool> hasSession() async {
    final cookies = await _cookieJar.loadForRequest(
      Uri.parse(ApiConfig.baseUrl),
    );
    return cookies.any((c) => c.name == 'session');
  }

  // --- Méthodes HTTP raccourcies ---

  Future<Response> get(String path, {Map<String, dynamic>? params}) {
    return dio.get(path, queryParameters: params);
  }

  Future<Response> post(String path, {dynamic data}) {
    return dio.post(path, data: data);
  }

  Future<Response> postForm(String path, {required Map<String, dynamic> data}) {
    return dio.post(
      path,
      data: FormData.fromMap(data),
      options: Options(contentType: 'application/x-www-form-urlencoded'),
    );
  }

  Future<Response> patch(String path, {dynamic data}) {
    return dio.patch(path, data: data);
  }

  Future<Response> delete(String path, {Map<String, dynamic>? params}) {
    return dio.delete(path, queryParameters: params);
  }

  /// POST qui retourne des bytes (pour TTS audio).
  Future<Response<List<int>>> postBytes(String path, {dynamic data}) {
    return dio.post<List<int>>(
      path,
      data: data,
      options: Options(responseType: ResponseType.bytes),
    );
  }
}
