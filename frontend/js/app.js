const state = {
            auth: {
                isLoggedIn: false,
                authMode: 'login',
                user: {
                    name: "Nguyễn Thế Hùng",
                    email: "student@hcmus.edu.vn",
                    role: "Sinh Viên / Người Học",
                    provider: "Email",
                    avatar: "https://api.dicebear.com/7.x/avataaars/svg?seed=HungNguyen"
                }
            },
            savedAccounts: [
                {
                    id: "acc_01",
                    name: "Nguyễn Thế Hùng",
                    email: "student@hcmus.edu.vn",
                    role: "FIT-HCMUS",
                    avatar: "https://api.dicebear.com/7.x/avataaars/svg?seed=HungNguyen"
                }
            ],
            profile: {
                goal: "Data Analyst Intern",
                weeklyHours: 4,
                selfReportedSkills: ["SQL Cơ bản", "Excel"]
            },
            skills: [
                { id: "SKILL_SQL", name: "SQL Truy vấn & Tổng hợp", weight: 0.30, target: 2, level: 2, isCore: true, measured: true },
                { id: "SKILL_DATA_QUALITY", name: "Chất lượng dữ liệu (Data Quality)", weight: 0.20, target: 2, level: 2, isCore: true, measured: true },
                { id: "SKILL_DATA_VIZ", name: "Trực quan hóa dữ liệu", weight: 0.20, target: 2, level: 0, isCore: false, measured: false },
                { id: "SKILL_PYTHON", name: "Python phân tích cơ bản", weight: 0.15, target: 1, level: 0, isCore: false, measured: false },
                { id: "SKILL_WRITTEN_COMM", name: "Báo cáo & Giải thích văn bản", weight: 0.15, target: 2, level: 0, isCore: false, measured: false }
            ],
            activities: [
                { id: "ACT_01", title: "Thực hành SQL Nâng Cao & Tối Ưu Làm Sạch", week: "Tuần 1-2", hours: 8, completed: true, prereq: null },
                { id: "ACT_02", title: "Trực Quan Hóa Dữ Liệu (Chart & Dashboard)", week: "Tuần 3-4", hours: 8, completed: false, prereq: "SKILL_SQL" },
                { id: "ACT_03", title: "Python Phân Tích Dữ Liệu Pandas Cơ Bản", week: "Tuần 5-6", hours: 8, completed: false, prereq: "ACT_02" },
                { id: "ACT_04", title: "Viết Báo Cáo Phân Tích Dữ Liệu Cuối Khóa", week: "Tuần 7-8", hours: 8, completed: false, prereq: "ACT_03" }
            ],
            history: [
                { time: "2026-10-22 09:00", event: "Khởi tạo Hồ sơ & Mục tiêu", version: "Profile_v1.0", detail: "Khai báo 4 giờ/tuần, mục tiêu Data Analyst" },
                { time: "2026-10-22 09:30", event: "Nộp bài thử DA01A", version: "Rubric_DA01_v3.0", detail: "Đạt SQL Mức 2, Data Quality Mức 2 (1,170,000 VNĐ)" }
            ],
            reminders: [
                { id: 1, text: "Hoạt động 'Trực Quan Hóa Dữ Liệu' (Tuần 3) sắp đến hạn!", type: "upcoming", active: true },
                { id: 2, text: "Hãy thực hiện bài Đánh Giá Lại DA01B để xác nhận tiến bộ.", type: "reassess", active: true }
            ]
        };

        // Demo persistence: only non-sensitive application data is stored locally.
        const STORAGE_KEY = "careeradapt-demo-v1";
        function persistState() {
            try {
                const snapshot = {
                    savedAccounts: state.savedAccounts,
                    profile: state.profile,
                    skills: state.skills,
                    activities: state.activities,
                    history: state.history.slice(0, 100),
                    reminders: state.reminders
                };
                localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
            } catch (error) {
                console.warn("Không thể lưu dữ liệu demo trên trình duyệt:", error);
            }
        }

        function restorePersistedState() {
            try {
                const raw = localStorage.getItem(STORAGE_KEY);
                if (!raw) return;
                const saved = JSON.parse(raw);
                if (Array.isArray(saved.savedAccounts)) state.savedAccounts = saved.savedAccounts;
                if (saved.profile && typeof saved.profile === "object") state.profile = { ...state.profile, ...saved.profile };
                if (Array.isArray(saved.skills)) state.skills = saved.skills;
                if (Array.isArray(saved.activities)) state.activities = saved.activities;
                if (Array.isArray(saved.history)) state.history = saved.history;
                if (Array.isArray(saved.reminders)) state.reminders = saved.reminders;
            } catch (error) {
                console.warn("Dữ liệu demo đã lưu không hợp lệ, sử dụng dữ liệu mặc định:", error);
            }
        }
        restorePersistedState();

        let selectedSavedAcc = null;
        let selectedTaskId = "DA01";

        /* HÀM KHỦNG KHỞI TẠO TIẾN TRÌNH VỀ 0 CHO TÀI KHOẢN MỚI */
        function resetUserProgressToZero() {
            state.skills.forEach(skill => {
                skill.level = 0;
                skill.measured = false;
            });

            state.activities.forEach(act => {
                act.completed = false;
            });

            const statusSql = document.getElementById('status-sql');
            const statusDq = document.getElementById('status-dq');
            const statusViz = document.getElementById('status-viz');
            const statusPy = document.getElementById('status-py');

            if (statusSql) { statusSql.className = "font-bold text-amber-600"; statusSql.innerText = "Chưa đánh giá"; }
            if (statusDq) { statusDq.className = "font-bold text-amber-600"; statusDq.innerText = "Chưa đánh giá"; }
            if (statusViz) { statusViz.className = "font-bold text-amber-600"; statusViz.innerText = "Chưa đánh giá"; }
            if (statusPy) { statusPy.className = "font-bold text-amber-600"; statusPy.innerText = "Chưa đánh giá"; }

            const metricCore = document.getElementById('metric-core');
            if (metricCore) {
                metricCore.className = "text-sm font-bold text-amber-600 mt-2";
                metricCore.innerHTML = `<i class="fa-solid fa-circle-exclamation"></i> CHƯA ĐẠT (0/2 Core Skills)`;
            }

            state.history = [{
                time: new Date().toLocaleString('vi-VN'),
                event: "Khởi tạo tài khoản mới",
                version: "Profile_v1.0",
                detail: "Tài khoản mới đăng ký thành công. Toàn bộ tiến trình khởi tạo về 0."
            }];

            renderGapTable();
            rebuildRoadmap();
            renderProgressList();
            renderHistory();
        }

        /* ========================================== */
        /* HỆ THỐNG XÁC THỰC AUTHENTICATION LOGIC     */
        /* ========================================== */

        function renderSavedAccounts() {
            const container = document.getElementById('saved-accounts-left-container');
            if (!container) return;

            if (!state.savedAccounts || state.savedAccounts.length === 0) {
                container.innerHTML = `
                    <h1 class="text-4xl sm:text-5xl font-black text-slate-900 leading-tight mb-4">
                        Khám phá những điều bạn <span class="text-indigo-600">yêu thích</span> trong nghề Data.
                    </h1>
                    <p class="text-slate-500 text-sm mb-6 leading-relaxed">
                        Hệ thống đánh giá năng lực thực chiến, đo lường khoảng cách kỹ năng (Skill Gap) và tự động xây dựng lộ trình học cá nhân hóa.
                    </p>
                    <div class="flex flex-wrap gap-2">
                        <span class="px-3 py-1.5 bg-indigo-50 text-indigo-700 font-bold text-xs rounded-full border border-indigo-100"><i class="fa-solid fa-database mr-1"></i>SQL Analysis (30%)</span>
                        <span class="px-3 py-1.5 bg-emerald-50 text-emerald-700 font-bold text-xs rounded-full border border-emerald-100"><i class="fa-solid fa-check-double mr-1"></i>Data Quality (20%)</span>
                    </div>
                `;
            } else {
                let cardsHTML = '';
                state.savedAccounts.forEach(acc => {
                    cardsHTML += `
                        <div class="saved-acc-card" onclick="loginWithSavedAccount('${acc.id}')" title="Bấm để đăng nhập bằng ${acc.name}">
                            <div class="saved-acc-remove" onclick="removeSavedAccount('${acc.id}', event)" title="Xóa tài khoản khỏi danh sách lưu">
                                <i class="fa-solid fa-xmark"></i>
                            </div>
                            <img src="${acc.avatar}" alt="${acc.name}" class="saved-acc-avatar">
                            <div class="saved-acc-info">
                                <p class="saved-acc-name">${acc.name}</p>
                                <p class="saved-acc-role">${acc.role}</p>
                            </div>
                        </div>
                    `;
                });

                cardsHTML += `
                    <div class="saved-acc-add-card" onclick="cancelQuickPassword(); switchAuthMode('login')" title="Đăng nhập tài khoản khác">
                        <div class="w-9 h-9 bg-indigo-100 text-indigo-600 rounded-full flex items-center justify-center text-base font-bold mb-1.5">
                            <i class="fa-solid fa-plus"></i>
                        </div>
                        <span class="text-xs font-bold">Thêm tài khoản</span>
                    </div>
                `;

                container.innerHTML = `
                    <h2 class="text-2xl font-black text-slate-900 mb-1">Đăng nhập gần đây</h2>
                    <p class="text-xs text-slate-500 mb-3">Nhấp vào hình ảnh của bạn hoặc thêm tài khoản.</p>
                    <div class="saved-acc-grid">
                        ${cardsHTML}
                    </div>
                `;
            }
        }

        /* BẤM VÀO AVATAR TÀI KHOẢN ĐÃ LƯU -> MỞ KHUNG NHẬP MẬT KHẨU */
        function loginWithSavedAccount(accId) {
            const acc = state.savedAccounts.find(a => a.id === accId);
            if (!acc) return;

            selectedSavedAcc = acc;

            document.getElementById('quick-pass-avatar').src = acc.avatar;
            document.getElementById('quick-pass-name').innerText = acc.name;
            document.getElementById('quick-pass-email').innerText = acc.email;
            document.getElementById('quick-password-input').value = '';

            document.getElementById('standard-auth-container').classList.add('hidden');
            document.getElementById('saved-acc-pass-container').classList.remove('hidden');

            setTimeout(() => {
                const passInput = document.getElementById('quick-password-input');
                if (passInput) passInput.focus();
            }, 100);
        }

        function cancelQuickPassword() {
            selectedSavedAcc = null;
            document.getElementById('standard-auth-container').classList.remove('hidden');
            document.getElementById('saved-acc-pass-container').classList.add('hidden');
        }

        function handleQuickPasswordSubmit(event) {
            if (event) event.preventDefault();
            if (!selectedSavedAcc) return;

            const passInput = document.getElementById('quick-password-input');
            if (!passInput || !passInput.value) {
                alert("Vui lòng nhập mật khẩu để tiếp tục!");
                return;
            }

            state.auth.user.name = selectedSavedAcc.name;
            state.auth.user.email = selectedSavedAcc.email;
            state.auth.user.role = selectedSavedAcc.role;
            state.auth.user.avatar = selectedSavedAcc.avatar;
            state.auth.user.provider = "Tài khoản đã lưu";
            state.auth.isLoggedIn = true;

            logAuthEvent(`Đăng nhập thành công qua mật khẩu tài khoản lưu: ${selectedSavedAcc.email}`);
            
            cancelQuickPassword();
            updateAuthUI();
        }

        function removeSavedAccount(accId, event) {
            if (event) event.stopPropagation();
            state.savedAccounts = state.savedAccounts.filter(a => a.id !== accId);
            if (selectedSavedAcc && selectedSavedAcc.id === accId) {
                cancelQuickPassword();
            }
            renderSavedAccounts();
        }

        function switchAuthMode(mode) {
            cancelQuickPassword();
            const loginForm = document.getElementById('form-login');
            const registerForm = document.getElementById('form-register');
            const btnTabLogin = document.getElementById('btn-tab-login');
            const btnTabRegister = document.getElementById('btn-tab-register');

            if (mode === 'login') {
                loginForm.classList.remove('hidden');
                registerForm.classList.add('hidden');
                if(btnTabLogin) btnTabLogin.className = "auth-pill-btn active";
                if(btnTabRegister) btnTabRegister.className = "auth-pill-btn";
            } else {
                loginForm.classList.add('hidden');
                registerForm.classList.remove('hidden');
                if(btnTabRegister) btnTabRegister.className = "auth-pill-btn active";
                if(btnTabLogin) btnTabLogin.className = "auth-pill-btn";
            }
        }

        function validatePasswordStrength(password) {
            return /^(?=.*[a-zA-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?])[A-Za-z\d!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]{8,}$/.test(password);
        }

        function togglePasswordVisibility(inputId, iconElement) {
            const input = document.getElementById(inputId);
            if (!input) return;
            if (input.type === 'password') {
                input.type = 'text';
                iconElement.classList.remove('fa-eye');
                iconElement.classList.add('fa-eye-slash');
            } else {
                input.type = 'password';
                iconElement.classList.remove('fa-eye-slash');
                iconElement.classList.add('fa-eye');
            }
        }

        function handlePreventPaste(event) {
            event.preventDefault();
            alert("Cảnh báo: Ô 'Xác nhận mật khẩu' không cho phép dán (Paste). Vui lòng gõ lại bằng tay!");
            return false;
        }

        /* HÀM ĐĂNG NHẬP THÔNG THƯỜNG */
        function handleLogin(event) {
            if (event) event.preventDefault();
            const inputEl = document.getElementById('login-email');
            const rememberCheck = document.getElementById('remember-me-checkbox');

            const val = inputEl && inputEl.value ? inputEl.value.trim() : "student@hcmus.edu.vn";
            const isEmail = val.includes('@');
            const nameVal = isEmail ? val.split('@')[0] : `Học viên (${val})`;

            state.auth.user.name = nameVal;
            state.auth.user.email = val;
            state.auth.user.role = "Sinh Viên / Người Học";
            state.auth.user.provider = isEmail ? "Email" : "Số điện thoại";
            state.auth.user.avatar = `https://api.dicebear.com/7.x/avataaars/svg?seed=${encodeURIComponent(nameVal)}`;
            state.auth.isLoggedIn = true;

            if (rememberCheck && rememberCheck.checked) {
                const exists = state.savedAccounts.some(a => a.email === val);
                if (!exists) {
                    state.savedAccounts.push({
                        id: "acc_" + Date.now(),
                        name: nameVal,
                        email: val,
                        role: isEmail ? "FIT-HCMUS" : "SĐT Học Viên",
                        avatar: state.auth.user.avatar
                    });
                }
            }

            logAuthEvent(`Đăng nhập thành công (${isEmail ? "Email" : "SĐT"}: ${val})`);
            updateAuthUI();
        }

        /* HÀM ĐĂNG KÝ MỚI HỖ TRỢ CẢ EMAIL LẪN SỐ ĐIỆN THOẠI & RESET TIẾN TRÌNH VỀ 0 */
        function handleRegister(event) {
            if (event) event.preventDefault();
            const nameInput = document.getElementById('reg-name').value;
            const regContactInput = document.getElementById('reg-email').value.trim();
            const passInput = document.getElementById('reg-password').value;
            const confirmPassInput = document.getElementById('reg-confirm-password').value;

            if (!validatePasswordStrength(passInput)) {
                alert("Mật khẩu chưa đủ mạnh!\n\nYêu cầu:\n- Tối thiểu 8 ký tự\n- Ít nhất 1 chữ cái, 1 chữ số, 1 ký tự đặc biệt (!@#$...)");
                return;
            }

            if (passInput !== confirmPassInput) {
                alert("Mật khẩu xác nhận không khớp!");
                return;
            }

            const isEmail = regContactInput.includes('@');

            state.auth.user.name = nameInput || "Học Viên Mới";
            state.auth.user.email = regContactInput;
            state.auth.user.provider = isEmail ? "Email" : "Số điện thoại";
            state.auth.user.avatar = `https://api.dicebear.com/7.x/avataaars/svg?seed=${encodeURIComponent(state.auth.user.name)}`;
            state.auth.isLoggedIn = true;

            state.savedAccounts.push({
                id: "acc_" + Date.now(),
                name: state.auth.user.name,
                email: regContactInput,
                role: isEmail ? "Thành viên mới" : "SĐT Thành viên mới",
                avatar: state.auth.user.avatar
            });

            resetUserProgressToZero();

            alert(`Chúc mừng ${state.auth.user.name}! Bạn đã đăng ký tài khoản thành công.\nToàn bộ tiến trình kỹ năng đã được khởi tạo về 0%.`);
            updateAuthUI();
        }

        function handleSocialLogin(provider) {
            state.auth.user.name = "Nguyễn Thế Hùng";
            state.auth.user.email = `${provider.toLowerCase()}.user@domain.com`;
            state.auth.user.provider = provider;
            state.auth.user.avatar = `https://api.dicebear.com/7.x/avataaars/svg?seed=${provider}`;
            state.auth.isLoggedIn = true;

            logAuthEvent(`Đăng nhập qua ${provider}`);
            updateAuthUI();
        }

        function handleGuestLogin() {
            state.auth.user.name = "Khách Trải Nghiệm";
            state.auth.user.email = "guest@careeradapt.ai";
            state.auth.user.provider = "Guest Mode";
            state.auth.isLoggedIn = true;

            resetUserProgressToZero();
            logAuthEvent("Vào hệ thống bằng Chế độ Khách (Khởi tạo tiến trình 0%)");
            updateAuthUI();
        }

        function handleLogout() {
            state.auth.isLoggedIn = false;
            updateAuthUI();
        }

        function logAuthEvent(detailText) {
            state.history.unshift({
                time: new Date().toLocaleString('vi-VN'),
                event: "Xác thực tài khoản",
                version: "Auth_v3.5",
                detail: detailText
            });
            renderHistory();
        }

        function updateAuthUI() {
            const loginScreen = document.getElementById('login-screen');
            const mainApp = document.getElementById('main-app');
            const userDisplay = document.getElementById('header-user-display');

            if (state.auth.isLoggedIn) {
                loginScreen.style.display = 'none';
                loginScreen.classList.add('hidden');

                mainApp.classList.remove('hidden');
                mainApp.style.display = 'flex';

                if (userDisplay) {
                    userDisplay.innerHTML = `
                        <div class="text-right text-xs">
                            <p class="font-bold text-slate-800">${state.auth.user.name} <span class="text-[10px] bg-indigo-100 text-indigo-700 font-normal px-1.5 py-0.2 rounded">${state.auth.user.provider}</span></p>
                            <p class="text-[10px] text-emerald-600 font-semibold"><i class="fa-solid fa-circle text-[8px] mr-1"></i>${state.auth.user.role}</p>
                        </div>
                        <button onclick="handleLogout()" class="px-2.5 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-600 font-bold text-xs rounded-lg transition border border-rose-200 flex items-center gap-1" title="Đăng xuất">
                            <i class="fa-solid fa-right-from-bracket"></i> Đăng xuất
                        </button>
                    `;
                }
            } else {
                loginScreen.style.display = 'flex';
                loginScreen.classList.remove('hidden');

                mainApp.classList.add('hidden');
                mainApp.style.display = 'none';

                renderSavedAccounts();
            }
        }

        /* ========================================== */
        /* CÁC CHỨC NĂNG USE CASES (UC01 - UC12) LOGIC*/
        /* ========================================== */

        function switchTab(tabId) {
            document.querySelectorAll('.tab-pane').forEach(el => el.classList.add('hidden'));
            document.getElementById(tabId).classList.remove('hidden');

            document.querySelectorAll('nav button').forEach(btn => {
                btn.classList.remove('active-tab');
                btn.classList.add('text-slate-500');
            });
            const activeBtn = document.getElementById('btn-' + tabId);
            if(activeBtn) {
                activeBtn.classList.add('active-tab');
                activeBtn.classList.remove('text-slate-500');
            }
        }

        function saveProfile(event) {
            event.preventDefault();
            const hoursInput = document.getElementById('input-weekly-hours');
            const hours = Number.parseInt(hoursInput.value, 10);
            if (!Number.isInteger(hours) || hours < 1 || hours > 20) {
                alert("Quỹ thời gian học phải là số nguyên từ 1 đến 20 giờ/tuần.");
                hoursInput.focus();
                return;
            }
            state.profile.weeklyHours = hours;
            document.getElementById('hours-limit-label').innerText = hours;
            
            state.history.unshift({
                time: new Date().toLocaleString('vi-VN'),
                event: "Cập nhật Hồ sơ (UC-01)",
                version: "Profile_v1.1",
                detail: `Cập nhật quỹ giờ: ${hours} giờ/tuần`
            });

            renderHistory();
            rebuildRoadmap();
            alert("Đã lưu hồ sơ thành công! Quỹ giờ mới: " + hours + "h/tuần.");
        }

        function openWorkspace(taskId) {
            selectedTaskId = taskId;
            const taskTitles = {
                DA01: "DA01A — Doanh thu cửa hàng",
                DA02: "DA02A — Biểu đồ và Python",
                DA03: "DA03A — Báo cáo phân tích"
            };
            document.getElementById('ws-title').innerText = `Không Gian Nộp Bài Thực Hành: ${taskTitles[taskId] || taskId}`;
            if (taskId !== "DA01") {
                alert("Đây là prototype: biểu mẫu nộp bài hiện được thiết kế chủ yếu cho DA01. Nội dung và định dạng nộp bài riêng cho " + taskId + " cần được triển khai tiếp.");
            }
            window.scrollTo({ top: document.getElementById('workspace-container').offsetTop - 80, behavior: 'smooth' });
        }

        function submitTask() {
            switchTab('tab-eval');
            window.scrollTo({ top: 0, behavior: 'smooth' });
            
            state.history.unshift({
                time: new Date().toLocaleString('vi-VN'),
                event: "Nộp bài thực hành (UC-03)",
                version: `Submission_${selectedTaskId}A`,
                detail: selectedTaskId === "DA01"
                    ? "Prototype ghi nhận thao tác nộp query.sql và result_da01.csv; chưa gửi dữ liệu đến Backend."
                    : `Prototype ghi nhận thao tác nộp bài ${selectedTaskId}; biểu mẫu và chấm điểm riêng chưa được tích hợp.`
            });
            renderHistory();
        }

        function simulateAITimeout() {
            const banner = document.getElementById('eval-status-banner');
            banner.className = "p-4 bg-amber-50 border border-amber-300 rounded-2xl flex justify-between items-center text-xs text-amber-900";
            banner.innerHTML = `
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 bg-amber-500 text-white rounded-xl flex items-center justify-center text-lg font-bold">
                        <i class="fa-solid fa-triangle-exclamation"></i>
                    </div>
                    <div>
                        <p class="font-bold text-amber-900 text-sm">Trạng thái: CẦN KIỂM TRA (Needs Review / Inconclusive)</p>
                        <p class="text-amber-800">Dịch vụ AI timeout hoặc phản hồi thiếu đoạn bằng chứng trích xuất. Bài nộp được giữ nguyên, KHÔNG gán mức 0.</p>
                    </div>
                </div>
                <span class="bg-amber-600 text-white font-bold px-3 py-1 rounded-full text-[11px]">Chưa Kết Luận</span>
            `;

            document.getElementById('criteria-list').innerHTML = `
                <div class="p-4 border border-amber-200 bg-amber-50/50 rounded-xl space-y-2 text-xs text-amber-900">
                    <p class="font-bold"><i class="fa-solid fa-spinner fa-spin mr-1"></i> Đánh giá bị hoãn - Đang chờ xử lý thủ công hoặc thử lại AI:</p>
                    <p>Theo quy tắc UC-04 & UC-05, khi AI mâu thuẫn hoặc thiếu bằng chứng, hệ thống không tự ghi đè điểm. Mức năng lực hiện tại của hồ sơ được giữ nguyên.</p>
                </div>
            `;
        }

        function resetEvaluationNormal() {
            location.reload();
        }

        function renderGapTable() {
            let totalMeasuredWeight = 0;
            let sumAttainment = 0;
            let coreSkillsValid = true;

            const tbody = document.getElementById('gap-table-body');
            if(!tbody) return;
            tbody.innerHTML = '';

            state.skills.forEach(skill => {
                if (skill.measured) {
                    totalMeasuredWeight += skill.weight;
                    const attainment = Math.min(skill.level / skill.target, 1.0);
                    sumAttainment += skill.weight * attainment;
                } else if (skill.isCore) {
                    coreSkillsValid = false;
                }

                const gap = skill.measured ? Math.max(0, skill.target - skill.level) : "Chưa đo";
                const statusBadge = skill.measured 
                    ? `<span class="bg-emerald-100 text-emerald-800 font-bold px-2 py-0.5 rounded text-[10px]">Mức ${skill.level} (Đã có bằng chứng)</span>`
                    : `<span class="bg-amber-100 text-amber-800 font-bold px-2 py-0.5 rounded text-[10px]">Chưa đánh giá</span>`;

                tbody.innerHTML += `
                    <tr class="hover:bg-slate-50 border-b">
                        <td class="p-2.5 font-bold">${skill.name}</td>
                        <td class="p-2.5">${skill.isCore ? '<span class="text-indigo-600 font-bold">Cốt lõi (Core)</span>' : 'Bổ trợ'}</td>
                        <td class="p-2.5 font-bold">${(skill.weight * 100).toFixed(0)}%</td>
                        <td class="p-2.5">Mức ${skill.target}</td>
                        <td class="p-2.5 font-bold">${skill.measured ? 'Mức ' + skill.level : '0'}</td>
                        <td class="p-2.5 font-bold ${gap > 0 ? 'text-amber-600' : 'text-emerald-600'}">${gap}</td>
                        <td class="p-2.5">${statusBadge}</td>
                    </tr>
                `;
            });

            const coveragePct = (totalMeasuredWeight * 100).toFixed(1);
            document.getElementById('metric-coverage').innerText = `${coveragePct}%`;

            const readinessBox = document.getElementById('readiness-box');
            if (totalMeasuredWeight >= 0.80 && coreSkillsValid) {
                const readinessVal = ((sumAttainment / totalMeasuredWeight) * 100).toFixed(1);
                readinessBox.className = "p-4 bg-emerald-50 border border-emerald-300 rounded-xl text-center text-xs";
                document.getElementById('metric-readiness').innerText = `${readinessVal}%`;
                document.getElementById('metric-readiness').className = "text-3xl font-black text-emerald-700 mt-1";
                document.getElementById('readiness-reason').innerText = "Đã đủ điều kiện Coverage ≥ 80% & đủ bằng chứng Core Skills.";
            } else {
                readinessBox.className = "p-4 bg-amber-50 border border-amber-200 rounded-xl text-center text-xs";
                document.getElementById('metric-readiness').innerText = "ĐANG BỊ ẨN";
                document.getElementById('metric-readiness').className = "text-lg font-bold text-amber-900 mt-1";
                document.getElementById('readiness-reason').innerHTML = `<i class="fa-solid fa-lock mr-1"></i> Khóa điểm tổng vì Coverage (${coveragePct}%) < 80%.`;
            }
        }

        function simulateFullCoverage() {
            state.skills.forEach(s => {
                s.measured = true;
                s.level = s.target;
            });
            document.getElementById('status-viz').className = "font-bold text-emerald-600";
            document.getElementById('status-viz').innerText = "Đã có bằng chứng";
            document.getElementById('status-py').className = "font-bold text-emerald-600";
            document.getElementById('status-py').innerText = "Đã có bằng chứng";
            
            renderGapTable();
            alert("Đã giả lập nộp đủ bài DA02 và DA03! Coverage = 100%. Điểm Readiness đã giải phóng.");
        }

        function rebuildRoadmap() {
            const container = document.getElementById('roadmap-weeks-container');
            if(!container) return;
            container.innerHTML = '';

            state.activities.forEach(act => {
                container.innerHTML += `
                    <div class="p-3.5 border-l-4 ${act.completed ? 'border-emerald-500 bg-slate-50' : 'border-indigo-500 bg-indigo-50/20'} rounded-r-xl flex justify-between items-center">
                        <div>
                            <span class="text-[10px] font-bold ${act.completed ? 'text-emerald-700' : 'text-indigo-700'}">${act.week} (${act.hours} Giờ) • ${act.completed ? 'ĐÃ HOÀN THÀNH' : 'SẮP TỚI'}</span>
                            <h4 class="font-bold text-sm text-slate-800 mt-0.5">${act.title}</h4>
                            <p class="text-[11px] text-slate-500">Ràng buộc tiên quyết: ${act.prereq ? act.prereq : 'Không có'}</p>
                        </div>
                        <div>
                            ${act.completed 
                                ? '<span class="bg-emerald-100 text-emerald-800 text-[10px] font-bold px-2.5 py-1 rounded-full"><i class="fa-solid fa-check mr-1"></i>Hoàn thành</span>' 
                                : '<span class="bg-indigo-600 text-white text-[10px] font-bold px-2.5 py-1 rounded-full">Theo lịch</span>'}
                        </div>
                    </div>
                `;
            });
        }

        function renderProgressList() {
            const container = document.getElementById('activity-progress-list');
            if(!container) return;
            container.innerHTML = '';

            state.activities.forEach(act => {
                container.innerHTML += `
                    <div class="p-3 border border-slate-200 bg-slate-50 rounded-xl flex justify-between items-center">
                        <div>
                            <p class="font-bold text-slate-800">${act.title}</p>
                            <p class="text-[10px] text-slate-500">${act.week} • Thời lượng: ${act.hours} giờ</p>
                        </div>
                        <button onclick="toggleActivityProgress('${act.id}')" class="px-3 py-1.5 ${act.completed ? 'bg-emerald-600 text-white' : 'bg-slate-200 text-slate-700 hover:bg-indigo-600 hover:text-white'} font-bold text-[11px] rounded-lg transition">
                            ${act.completed ? '<i class="fa-solid fa-check mr-1"></i>Đã xong' : 'Đánh dấu Hoàn thành'}
                        </button>
                    </div>
                `;
            });
        }

        function toggleActivityProgress(actId) {
            const act = state.activities.find(a => a.id === actId);
            if(act) {
                act.completed = !act.completed;
                renderProgressList();
                rebuildRoadmap();

                state.history.unshift({
                    time: new Date().toLocaleString('vi-VN'),
                    event: "Cập nhật tiến độ học (UC-09)",
                    version: "Progress_v1.0",
                    detail: `Đánh dấu '${act.title}' -> ${act.completed ? 'Hoàn thành' : 'Chưa xong'}`
                });
                renderHistory();
            }
        }

        function triggerReassessment() {
            alert("Đã bắt đầu bài Đánh Giá Lại DA01B (Biến thể tương đương).\nKết quả so sánh tiến bộ sẽ được ghi nhận vào lịch sử.");
            state.history.unshift({
                time: new Date().toLocaleString('vi-VN'),
                event: "Thực hiện Đánh Giá Lại (UC-10)",
                version: "Assessment_DA01B_v3.0",
                detail: "Hoàn thành bài A/B variant. Cập nhật so sánh tiến bộ."
            });
            renderHistory();
            switchTab('tab-progress');
        }

        function renderHistory() {
            const tbody = document.getElementById('history-table-body');
            if(!tbody) return;
            tbody.innerHTML = '';

            state.history.forEach(item => {
                tbody.innerHTML += `
                    <tr class="hover:bg-slate-50 border-b">
                        <td class="p-2.5 font-mono text-[11px]">${item.time}</td>
                        <td class="p-2.5 font-bold text-slate-800">${item.event}</td>
                        <td class="p-2.5"><span class="bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded font-mono text-[10px]">${item.version}</span></td>
                        <td class="p-2.5 text-slate-600">${item.detail}</td>
                    </tr>
                `;
            });
        }

        function toggleReminderDrawer() {
            const dropdown = document.getElementById('reminder-dropdown');
            if(dropdown) dropdown.classList.toggle('hidden');
        }

        function renderReminders() {
            const list = document.getElementById('reminder-list');
            if(!list) return;
            list.innerHTML = '';

            state.reminders.forEach(rem => {
                list.innerHTML += `
                    <div class="p-2 bg-indigo-50/50 border border-indigo-100 rounded-lg flex items-start gap-2">
                        <i class="fa-solid fa-bell text-indigo-600 mt-0.5"></i>
                        <div>
                            <p class="text-slate-800 font-bold">${rem.text}</p>
                            <span class="text-[9px] text-slate-400">Điều kiện: Hoạt động sắp/quá hạn</span>
                        </div>
                    </div>
                `;
            });
        }

        // Persist demo mutations without storing passwords or authentication secrets.
        function persistAfterAction(functionName) {
            const original = window[functionName];
            if (typeof original !== "function") return;
            window[functionName] = function (...args) {
                const result = original.apply(this, args);
                persistState();
                return result;
            };
        }
        [
            "handleLogin", "handleRegister", "handleSocialLogin", "handleGuestLogin",
            "handleLogout", "removeSavedAccount", "saveProfile", "submitTask",
            "simulateFullCoverage", "toggleActivityProgress", "triggerReassessment",
            "resetUserProgressToZero"
        ].forEach(persistAfterAction);

        /* KHỞI TẠO DỮ LIỆU KHI TẢI TRANG */
        window.addEventListener('DOMContentLoaded', () => {
            const hoursInput = document.getElementById('input-weekly-hours');
            const hoursLabel = document.getElementById('hours-limit-label');
            if (hoursInput) hoursInput.value = state.profile.weeklyHours;
            if (hoursLabel) hoursLabel.innerText = state.profile.weeklyHours;
            updateAuthUI();
            renderGapTable();
            rebuildRoadmap();
            renderProgressList();
            renderHistory();
            renderReminders();
        });
