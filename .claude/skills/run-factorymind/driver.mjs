#!/usr/bin/env node
/**
 * driver.mjs — تشغيل واجهة Streamlit وقيادتها برمجياً.
 *
 * لماذا لا يكفي curl: Streamlit يردّ HTTP 200 بهيكل HTML فارغ ثم يُصيّر
 * كل شيء عبر JavaScript. curl يرى صفحة ناجحة حتى لو كان التطبيق يعرض
 * رسالة خطأ. الحكم الوحيد الصادق هو متصفح حقيقي يقرأ الـ DOM بعد التصيير.
 *
 * التطبيق متعدد الصفحات منذ Phase 6 (st.navigation). الصفحة الافتراضية
 * "النظرة التنفيذية" تقرأ من قاعدة البيانات ولا تحسب — فتبدأ فارغة حتى
 * تُشغَّل الدفعة. مرّر مسار الصفحة للوصول إلى غيرها.
 *
 *   node .claude/skills/run-factorymind/driver.mjs shot
 *   node .claude/skills/run-factorymind/driver.mjs text forecasting
 *   node .claude/skills/run-factorymind/driver.mjs pages   # يزور الخمس
 *   node .claude/skills/run-factorymind/driver.mjs flow
 */
import { chromium } from 'playwright';
import { spawn, execSync } from 'node:child_process';
import { mkdirSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const SKILL_DIR = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(SKILL_DIR, '..', '..', '..');
const SHOTS = join(SKILL_DIR, 'screenshots');
const PORT = process.env.PORT || 8701;
const URL = `http://localhost:${PORT}`;
const PYTHON = join(ROOT, '.venv', 'bin', 'python');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** انتظار المنفذ — لا sleep ثابت. Streamlit يستغرق 10-15s على هذه الآلة. */
async function waitForPort(timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(URL);
      if (res.ok) return true;
    } catch {}
    await sleep(500);
  }
  throw new Error(`الخادم لم يستجب على ${URL} خلال ${timeoutMs / 1000}s`);
}

/** الـ schema مملوكة لـ migrations/ — التطبيق يتحقق ولا يُنشئ. */
function requireSchema() {
  try {
    execSync(`"${PYTHON}" -c "import sys; sys.path.insert(0,'${ROOT}'); ` +
             `from migrate import missing_tables; from config import DATABASE_PATH; ` +
             `sys.exit(1 if missing_tables(DATABASE_PATH) else 0)"`,
             { cwd: ROOT, stdio: 'ignore' });
  } catch {
    console.error('✗ قاعدة البيانات ناقصة جداول. شغّل أولاً:\n  python migrate.py');
    process.exit(1);
  }
}

async function launch() {
  requireSchema();
  // منفذ عالق من تشغيل سابق يجعل Streamlit يختار منفذاً آخر بصمت
  try { execSync(`pkill -f "streamlit run app.py --server.port ${PORT}"`); } catch {}

  const server = spawn(
    PYTHON,
    ['-m', 'streamlit', 'run', 'app.py',
     '--server.headless', 'true',        // بدونه يحاول فتح متصفح ويعلّق
     '--server.port', String(PORT),
     '--browser.gatherUsageStats', 'false'],
    { cwd: ROOT, stdio: ['ignore', 'pipe', 'pipe'] }
  );

  // السجل يُجمَّع ولا يُمرَّر: Streamlit يطبع تحذيرات إهمال غزيرة على
  // stderr (use_container_width...) تُغرق مخرجات الـ driver. يُطبع عند
  // الفشل فقط.
  let log = '';
  server.stdout.on('data', (d) => { log += d; });
  server.stderr.on('data', (d) => { log += d; });
  server.on('exit', (code) => {
    if (code !== 0 && code !== null) {
      console.error(`✗ الخادم انتهى بالكود ${code}\n${log.slice(-800)}`);
      process.exit(1);
    }
  });

  await waitForPort();
  return { server, log: () => log };
}

/**
 * مسارات الصفحات — تطابق url_path في app.py، باستثناء واحد:
 * الصفحة الافتراضية (default=True) تُخدَّم على الجذر '' لا على url_path
 * الخاص بها. زيارة /executive تعمل ظاهرياً لكن Streamlit يسجّل
 * "The page that you have requested does not seem to exist" ويتراجع
 * إلى الرئيسية — التي هي executive نفسها، فيبدو كل شيء سليماً.
 */
const PAGES = [
  '', 'forecasting', 'product-intelligence',
  'advanced-analytics', 'purchase-plan',
];
const PAGE_LABEL = (path) => path || 'executive (الجذر)';

async function openPage(browser, path = '') {
  const page = await browser.newPage({ viewport: { width: 1500, height: 1100 } });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(path ? `${URL}/${path}` : URL, { waitUntil: 'networkidle' });

  // الشاهد على التصيير هو h1 لا stMetric: الصفحة التنفيذية تبدأ بلا
  // مؤشرات (تقرأ من قاعدة بيانات فارغة)، وانتظار stMetric كان يعلّق 60s
  // على تطبيق سليم تماماً.
  await page.waitForSelector('h1', { timeout: 60000 });
  await sleep(2500);  // تصيير Plotly وجداول Streamlit يلحق الـ h1
  return { page, errors };
}

/** استثناءات Streamlit تظهر في الصفحة لا في console — يجب فحصها صراحةً. */
async function pageExceptions(page) {
  return page.$$eval('[data-testid="stException"]', (nodes) =>
    nodes.map((n) => n.innerText.slice(0, 160).replace(/\n+/g, ' '))
  );
}

/** Streamlit يعيد التشغيل عند كل تفاعل — انتظر هدوء الشبكة لا مدة ثابتة. */
async function settle(page) {
  await page.waitForLoadState('networkidle');
  await sleep(800);
}

const COMMANDS = {
  async shot({ page, target }) {
    mkdirSync(SHOTS, { recursive: true });
    const path = join(SHOTS, `${target || 'app'}.png`);
    await page.screenshot({ path, fullPage: false });
    console.log(`✓ لقطة: ${path}`);
  },

  async text({ page }) {
    const title = await page.textContent('h1');
    console.log(`العنوان: ${title?.trim()}`);
    const metrics = await page.$$eval('[data-testid="stMetric"]', (nodes) =>
      nodes.slice(0, 6).map((n) => n.innerText.replace(/\n+/g, ' = ').trim())
    );
    if (metrics.length) {
      console.log('المؤشرات:');
      metrics.forEach((m) => console.log(`  ${m}`));
    }
    const alerts = await page.$$eval('[data-testid="stAlert"]', (nodes) =>
      nodes.slice(0, 3).map((n) => n.innerText.slice(0, 90).replace(/\n+/g, ' '))
    );
    if (alerts.length) {
      console.log('تنبيهات:');
      alerts.forEach((a) => console.log(`  ${a}`));
    }
    console.log(`رسوم Plotly مُصيَّرة: ${(await page.$$('.js-plotly-plot')).length}`);
  },

  /** يزور الصفحات الخمس ويلتقط لقطة لكل واحدة. يفشل عند أي استثناء. */
  async pages({ page, browser }) {
    mkdirSync(SHOTS, { recursive: true });
    const broken = [];

    for (const path of PAGES) {
      await page.goto(path ? `${URL}/${path}` : URL, { waitUntil: 'networkidle' });
      await page.waitForSelector('h1', { timeout: 60000 });
      // التنبؤ وذكاء المنتج يُدرّبان نماذج عند الفتح — أبطأ من الباقي
      await sleep(path === 'forecasting' || path === 'product-intelligence' ? 9000 : 4000);

      const title = (await page.textContent('h1'))?.trim() ?? '?';
      const exceptions = await pageExceptions(page);
      const metrics = (await page.$$('[data-testid="stMetric"]')).length;
      const charts = (await page.$$('.js-plotly-plot')).length;
      await page.screenshot({ path: join(SHOTS, `page-${path || 'executive'}.png`) });

      const status = exceptions.length ? `✗ ${exceptions[0]}` : 'ok';
      console.log(`${PAGE_LABEL(path).padEnd(24)} ${String(metrics).padStart(2)} مؤشر  ` +
                  `${String(charts).padStart(2)} رسم  ${title.slice(0, 20).padEnd(22)} ${status}`);
      if (exceptions.length) broken.push(PAGE_LABEL(path));
    }

    if (broken.length) throw new Error(`صفحات بها استثناءات: ${broken.join(', ')}`);
    console.log(`\n✓ الصفحات الخمس تُصيَّر بلا استثناء — لقطات في ${SHOTS}/`);
  },

  /**
   * تدفق مستخدم حقيقي: مدّد أفق التنبؤ وتحقق أن التطبيق أعاد التصيير.
   *
   * الشاهد هو قيمة الشريط لا "قيمة التنبؤ (أول شهر)": تمديد الأفق من 6
   * إلى 12 لا يغيّر تنبؤ الشهر الأول — وهذا صحيح لا عطل. الأثر المرئي
   * هو اتساع نطاق التنبؤ في الرسم (قارن flow-before.png بـ flow-after.png).
   */
  async flow({ page }) {
    mkdirSync(SHOTS, { recursive: true });
    const readSteps = () =>
      page.$eval('[data-testid="stSlider"] input[type="range"]', (el) => el.value);

    const before = await readSteps();
    console.log(`أفق التنبؤ قبل: ${before} أشهر`);
    await page.screenshot({ path: join(SHOTS, 'flow-before.png') });

    // شريط "عدد الأشهر للتنبؤ".
    // ⚠️ ليس [role="slider"] — النمط الشائع في Playwright لا ينطبق هنا.
    // Streamlit 1.59 يُصيّر input[type=range] أصلياً؛ فحص الـ DOM يعطي
    // role=slider: 0 مقابل input[type=range]: 1. وهو الوحيد في الصفحة.
    const slider = await page.$('[data-testid="stSlider"] input[type="range"]');
    if (!slider) throw new Error('لم أجد شريط أفق التنبؤ (input[type=range])');

    // ⚠️ focus() لا click(). الـ input مرئي (129×16، opacity=1) لكن
    // Streamlit يضع مقبضاً مخصّصاً فوقه يعترض أحداث المؤشر، فتنتهي مهلة
    // click بعد 30s على فحص القابلية. focus() يتجاوز ذلك.
    // وfill() لا يصلح بديلاً: ضبط القيمة برمجياً لا يُطلق دورة إعادة
    // تشغيل Streamlit، فتتغيّر القيمة ولا يتغيّر شيء آخر.
    await slider.focus();
    for (let i = 0; i < 6; i++) {
      await page.keyboard.press('ArrowRight');
      await sleep(300);  // كل ضغطة تُطلق rerun — التتابع السريع يُسقط بعضها
    }
    await settle(page);

    const after = await readSteps();
    await page.screenshot({ path: join(SHOTS, 'flow-after.png') });
    console.log(`أفق التنبؤ بعد: ${after} أشهر`);

    if (after === before) {
      throw new Error('الشريط لم يتحرّك — لم تصل ضغطات المفاتيح');
    }
    console.log('✓ التدفق نُفِّذ — التطبيق أعاد التصيير');
    console.log(`  لقطات: ${SHOTS}/flow-{before,after}.png`);
    console.log('  (نطاق التنبؤ في الرسم يتّسع — قارن اللقطتين)');
  },
};

async function main() {
  const command = process.argv[2] || 'shot';
  let target = process.argv[3] || '';
  if (!COMMANDS[command]) {
    console.error(`أوامر متاحة: ${Object.keys(COMMANDS).join(', ')}`);
    console.error(`صفحات: ${PAGES.join(', ')}`);
    process.exit(1);
  }
  // 'executive' اسم مقبول من المستخدم، لكنه يُخدَّم على الجذر
  if (target === 'executive') target = '';
  if (target && !PAGES.includes(target)) {
    console.error(`صفحة غير معروفة: ${target}\nالمتاح: ${PAGES.map(PAGE_LABEL).join(', ')}`);
    process.exit(1);
  }
  // شريط أفق التنبؤ في التحليل المتقدّم — الصفحة الوحيدة التي تملكه
  if (command === 'flow') target = 'advanced-analytics';

  const { server, log } = await launch();
  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  let code = 0;
  try {
    const { page, errors } = await openPage(browser, target);
    await COMMANDS[command]({ page, browser, target });

    // استثناء بايثون يُصيَّر داخل الصفحة ولا يصل console — التطبيق "يعمل"
    // بينما يعرض stack trace. الفحص صريح لهذا السبب.
    const exceptions = command === 'pages' ? [] : await pageExceptions(page);
    if (exceptions.length) {
      console.error(`\n✗ استثناء في الصفحة:\n  ${exceptions[0]}`);
      code = 1;
    }
    if (errors.length) {
      console.log(`\n⚠ أخطاء console (${errors.length}):`);
      errors.slice(0, 3).forEach((e) => console.log(`  ${e.slice(0, 120)}`));
    }
  } catch (err) {
    // السجل أولاً والخطأ أخيراً: تحذيرات إهمال Streamlit تملأ مئات
    // الأسطر، و`| tail` كان يبتلع رسالة الخطأ لو طُبعت قبلها.
    console.error(`--- آخر سجل الخادم ---\n${log().slice(-400)}`);
    console.error(`\n✗ ${err.message}`);
    code = 1;
  } finally {
    await browser.close();
    server.kill('SIGTERM');
    await sleep(500);
    try { execSync(`pkill -f "streamlit run app.py --server.port ${PORT}"`); } catch {}
  }
  process.exit(code);
}

main();
