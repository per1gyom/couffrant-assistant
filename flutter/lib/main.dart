import 'package:flutter/material.dart';
import 'services/api_service.dart';
import 'services/auth_service.dart';
import 'screens/login_screen.dart';
import 'screens/chat_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const RayaApp());
}

class RayaApp extends StatelessWidget {
  const RayaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Raya',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF0F1117),
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF22C55E),
          brightness: Brightness.dark,
        ),
      ),
      home: const SplashScreen(),
    );
  }
}

/// Ecran de chargement initial.
/// Initialise le client HTTP et verifie la session.
/// En cas d'erreur, redirige vers le login.
class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    bool loggedIn = false;

    try {
      // Initialiser le client HTTP
      await ApiService.instance.init();

      // Verifier si une session active existe (timeout 5s)
      final authService = AuthService();
      loggedIn = await authService.isLoggedIn()
          .timeout(const Duration(seconds: 5), onTimeout: () => false);
    } catch (_) {
      // En cas d'erreur, on va au login
      loggedIn = false;
    }

    if (!mounted) return;

    Navigator.of(context).pushReplacement(
      MaterialPageRoute(
        builder: (_) => loggedIn ? const ChatScreen() : const LoginScreen(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F1117),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 72,
              height: 72,
              decoration: BoxDecoration(
                color: const Color(0xFF22C55E),
                borderRadius: BorderRadius.circular(20),
              ),
              child: const Center(
                child: Text(
                  '\u2726',
                  style: TextStyle(fontSize: 36, color: Colors.white),
                ),
              ),
            ),
            const SizedBox(height: 24),
            const SizedBox(
              width: 24,
              height: 24,
              child: CircularProgressIndicator(
                strokeWidth: 2.5,
                color: Color(0xFF22C55E),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
