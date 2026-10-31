import android.graphics.Bitmap;
import android.os.IBinder;
import java.io.ByteArrayOutputStream;
import dalvik.system.PathClassLoader;
import android.net.LocalServerSocket;
import android.net.LocalSocket;
import java.io.DataOutputStream;

/** On-demand, full-resolution capture. No service, storage permission or cached frames. */
public final class MaaNativeCap {
    private static Class<?> displayControl;
    private static float frameScale = 1.0f;
    public static void main(String[] args) {
        if (args.length > 0 && args[0].equals("--serve")) {
            try {
                LocalServerSocket server = new LocalServerSocket("maa-native-cap");
                boolean running = true;
                while (running) {
                    try (LocalSocket socket = server.accept()) {
                        int request = socket.getInputStream().read();
                        if (request == 'P') {
                            socket.getOutputStream().write('K');
                            socket.getOutputStream().flush();
                            continue;
                        }
                        if (request == 'Q') {
                            socket.getOutputStream().write('K');
                            socket.getOutputStream().flush();
                            running = false;
                            continue;
                        }
                        if (request != 'C') continue;
                        long captureStart = System.nanoTime();
                        byte[] frame = capture(95);
                        long captured = System.nanoTime();
                        DataOutputStream output = new DataOutputStream(socket.getOutputStream());
                        output.writeInt(frame.length);
                        output.write(frame);
                        output.flush();
                        System.err.println("frame capture_ms=" + ((captured-captureStart)/1000000) + " write_ms=" + ((System.nanoTime()-captured)/1000000) + " bytes=" + frame.length);
                    } catch (Exception e) { e.printStackTrace(System.err); }
                }
                server.close();
                System.exit(0); // app_process may retain Android runtime threads after main returns.
            } catch (Exception e) { e.printStackTrace(System.err); System.exit(1); }
            return;
        }
        try {
            int quality = args.length == 0 ? 95 : Integer.parseInt(args[0]);
            if (quality < 90 || quality > 100) throw new IllegalArgumentException("quality must be 90..100");
            System.out.write(capture(quality));
            System.out.flush();
        } catch (Throwable e) {
            e.printStackTrace(System.err);
            System.exit(1);
        }
    }

    private static byte[] capture(int quality) throws Exception {
            Class<?> control = displayControl;
            if (control == null) {
            try { control = Class.forName("com.android.server.display.DisplayControl"); }
            catch (ClassNotFoundException e) {
                String classPath = System.getenv("SYSTEMSERVERCLASSPATH");
                if (classPath == null) classPath = "/system/framework/services.jar";
                control = new PathClassLoader(classPath, ClassLoader.getSystemClassLoader())
                    .loadClass("com.android.server.display.DisplayControl");
                java.lang.reflect.Method load = Runtime.class.getDeclaredMethod("loadLibrary0", Class.class, String.class);
                load.setAccessible(true);
                load.invoke(Runtime.getRuntime(), control, "android_servers");
            }
            displayControl = control;
            }
            long[] ids = (long[]) control.getMethod("getPhysicalDisplayIds").invoke(null);
            if (ids == null || ids.length != 1) throw new IllegalStateException("expected one physical display");
            IBinder token = (IBinder) control.getMethod("getPhysicalDisplayToken", long.class).invoke(null, ids[0]);
            Class<?> capture = Class.forName("android.window.ScreenCapture");
            Class<?> builderType = Class.forName("android.window.ScreenCapture$DisplayCaptureArgs$Builder");
            Object builder = builderType.getConstructor(IBinder.class).newInstance(token);
            // Capture at the recognition height without changing the phone display.
            if (frameScale < 1.0f) {
                builderType.getMethod("setFrameScale", float.class).invoke(builder, frameScale);
            }
            Object captureArgs = builderType.getMethod("build").invoke(builder);
            Class<?> argsType = Class.forName("android.window.ScreenCapture$DisplayCaptureArgs");
            Object buffer = capture.getMethod("captureDisplay", argsType).invoke(null, captureArgs);
            if (buffer == null) throw new IllegalStateException("screen capture failed");
            Bitmap hardware = (Bitmap) buffer.getClass().getMethod("asBitmap").invoke(buffer);
            if (hardware == null) throw new IllegalStateException("empty bitmap");
            if (frameScale == 1.0f) {
                frameScale = Math.min(1.0f, 720.0f / Math.min(hardware.getWidth(), hardware.getHeight()));
            }
            Bitmap bitmap = hardware.copy(Bitmap.Config.ARGB_8888, false);
            // Some vendor capture implementations ignore setFrameScale.
            // Resize the capture, never the display, before JPEG compression.
            int shortSide = Math.min(bitmap.getWidth(), bitmap.getHeight());
            if (shortSide > 720) {
                float scale = 720.0f / shortSide;
                Bitmap resized = Bitmap.createScaledBitmap(bitmap,
                    Math.round(bitmap.getWidth() * scale), Math.round(bitmap.getHeight() * scale), true);
                bitmap.recycle();
                bitmap = resized;
            }
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            if (!bitmap.compress(Bitmap.CompressFormat.JPEG, quality, output)) {
                throw new IllegalStateException("JPEG encoding failed");
            }
            bitmap.recycle();
            hardware.recycle();
            Object nativeBuffer = buffer.getClass().getMethod("getHardwareBuffer").invoke(buffer);
            if (nativeBuffer instanceof AutoCloseable) ((AutoCloseable) nativeBuffer).close();
            return output.toByteArray();
    }
}
