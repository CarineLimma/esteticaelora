
(function () {
    "use strict";

    const $ = (selector, root = document) => root.querySelector(selector);
    const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

    const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
    const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

 

    const navItems = $$(".nav-item[data-section]");
    const adminSections = $$(".admin-section");
    const pageTitle = $(".topbar-title span");
    const pageSubtitle = $(".topbar-title small");

    const sidebar = $("#sidebar");
    const overlay = $("#sidebarOverlay");
    const menuToggle = $("#menuToggle");
    const closeSidebar = $("#closeSidebar");

    function setSidebar(open) {
        if (sidebar) sidebar.classList.toggle("open", open);
        if (overlay) overlay.classList.toggle("open", open);

        if (menuToggle) {
            menuToggle.setAttribute("aria-expanded", String(open));
        }
    }

    function navigateToSection(target) {
        const section = document.getElementById("section-" + target);

        if (!section) {
            console.error("Seção não encontrada:", "section-" + target);
            return;
        }

        navItems.forEach(item => {
            item.classList.toggle(
                "active",
                item.dataset.section === target
            );
        });

        adminSections.forEach(item => {
            item.classList.toggle("active", item === section);
        });

        const activeButton = navItems.find(
            item => item.dataset.section === target
        );

        if (pageTitle && activeButton) {
            pageTitle.textContent = activeButton.textContent.trim();
        }

        if (pageSubtitle) {
            pageSubtitle.textContent = "Gerencie seu espaço";
        }

        setSidebar(false);

        window.scrollTo({
            top: 0,
            behavior: "smooth"
        });
    }

    navItems.forEach(button => {
        button.addEventListener("click", () => {
            navigateToSection(button.dataset.section);
        });
    });

    $$("[data-go]").forEach(button => {
        button.addEventListener("click", () => {
            navigateToSection(button.dataset.go);
        });
    });

    if (menuToggle) {
        menuToggle.addEventListener("click", () => {
            setSidebar(!sidebar?.classList.contains("open"));
        });
    }

    if (closeSidebar) {
        closeSidebar.addEventListener("click", () => setSidebar(false));
    }

    if (overlay) {
        overlay.addEventListener("click", () => setSidebar(false));
    }

    document.addEventListener("keydown", event => {
        if (event.key === "Escape") {
            setSidebar(false);
        }
    });

  

    $$(".flash").forEach(flash => {
        setTimeout(() => {
            flash.style.opacity = "0";

            setTimeout(() => {
                const list = flash.parentElement;
                flash.remove();

                if (
                    list &&
                    list.classList.contains("flash-list") &&
                    !list.children.length
                ) {
                    list.remove();
                }
            }, 400);
        }, 6000);
    });

  

    $$("form[data-confirm]").forEach(form => {
        form.addEventListener("submit", event => {
            if (!window.confirm(form.dataset.confirm)) {
                event.preventDefault();
            }
        });
    });

 

    $$("form").forEach(form => {
        form.addEventListener("submit", event => {
            if (event.defaultPrevented) return;

            const buttons = $$('button[type="submit"]', form);

            setTimeout(() => {
                buttons.forEach(button => {
                    button.disabled = true;
                });
            }, 0);
        });
    });

    window.addEventListener("pageshow", () => {
        $$('button[type="submit"]:disabled').forEach(button => {
            button.disabled = false;
        });
    });

  

    const filterDate = $("#filterAppointmentDate");
    const appointmentsTable = $("#appointmentsTable");
    const noAppointmentsRow = $("#noAppointmentsRow");

    if (filterDate && appointmentsTable) {
        filterDate.addEventListener("input", () => {
            const value = filterDate.value;
            let visible = 0;

            $$("tr[data-date]", appointmentsTable).forEach(row => {
                const show = !value || row.dataset.date === value;

                row.hidden = !show;

                if (show) visible++;
            });

            if (noAppointmentsRow) {
                noAppointmentsRow.hidden = visible > 0;
            }
        });
    }

   

    $$(".schedule-row").forEach(row => {
        const checkbox = $(".day-enabled", row);
        const start = $(".day-start", row);
        const end = $(".day-end", row);

        if (!checkbox || !start || !end) return;

        function updateScheduleFields() {
            start.disabled = !checkbox.checked;
            end.disabled = !checkbox.checked;
        }

        checkbox.addEventListener("change", updateScheduleFields);
        updateScheduleFields();
    });

    const scheduleForm = $("#scheduleForm");

    if (scheduleForm) {
        scheduleForm.addEventListener("submit", event => {
            for (const row of $$(".schedule-row", scheduleForm)) {
                const checkbox = $(".day-enabled", row);
                const start = $(".day-start", row);
                const end = $(".day-end", row);

                if (!checkbox || !start || !end) continue;

                if (
                    checkbox.checked &&
                    (!start.value || !end.value || start.value >= end.value)
                ) {
                    event.preventDefault();

                    const name = $("strong", row)?.textContent.trim() || "dia";

                    alert(
                        "Em " + name +
                        ", o horário de início precisa ser antes do término."
                    );

                    start.focus();
                    return;
                }
            }
        });
    }



    const blockedDate = $("#blockedDate");

    if (blockedDate) {
        const now = new Date();
        const pad = number => String(number).padStart(2, "0");

        blockedDate.min =
            now.getFullYear() + "-" +
            pad(now.getMonth() + 1) + "-" +
            pad(now.getDate());
    }



    const serviceModal = $("#serviceModal");
    const serviceForm = $("#serviceForm");

    if (serviceModal && serviceForm) {
        const title = $("#serviceModalTitle");

        const fields = {
            id: $("#serviceId"),
            name: $("#serviceName"),
            description: $("#serviceDescription"),
            price: $("#servicePrice"),
            duration: $("#serviceDuration"),
            photo: $("#servicePhoto")
        };

        let lastFocus = null;

        function openModal(mode, data = null) {
            lastFocus = document.activeElement;

            serviceForm.reset();
            fields.id.value = "";

            if (mode === "edit" && data) {
                title.textContent = "Editar serviço";
                fields.id.value = data.id || "";
                fields.name.value = data.name || "";
                fields.description.value = data.description || "";
                fields.price.value = data.price || "";
                fields.duration.value = data.duration || "";
            } else {
                title.textContent = "Adicionar serviço";
            }

            serviceModal.classList.add("active");
            document.body.style.overflow = "hidden";
            fields.name.focus();
        }

        function closeModal() {
            serviceModal.classList.remove("active");
            document.body.style.overflow = "";

            if (lastFocus) lastFocus.focus();
        }

        const addButton = $("#addServiceButton");

        if (addButton) {
            addButton.addEventListener("click", () => openModal("add"));
        }

        $$(".edit-service").forEach(button => {
            button.addEventListener("click", () => {
                openModal("edit", button.dataset);
            });
        });

        const closeButton = $("#closeServiceModal");

        if (closeButton) {
            closeButton.addEventListener("click", closeModal);
        }

        serviceModal.addEventListener("click", event => {
            if (event.target === serviceModal) closeModal();
        });

        document.addEventListener("keydown", event => {
            if (
                event.key === "Escape" &&
                serviceModal.classList.contains("active")
            ) {
                closeModal();
            }
        });
    }

  

    function validImage(input) {
        const file = input.files && input.files[0];

        if (!file) return null;

        if (!IMAGE_TYPES.includes(file.type)) {
            alert("Formato inválido. Use JPG, PNG ou WEBP.");
            input.value = "";
            return null;
        }

        if (file.size > MAX_IMAGE_BYTES) {
            alert("A imagem deve ter no máximo 5 MB.");
            input.value = "";
            return null;
        }

        return file;
    }

 

    function bindPreview(inputSelector, previewSelector) {
        const input = $(inputSelector);
        const preview = $(previewSelector);

        if (!input || !preview) return;

        let currentURL = null;

        input.addEventListener("change", () => {
            const file = validImage(input);

            if (!file) return;

            if (currentURL) URL.revokeObjectURL(currentURL);

            currentURL = URL.createObjectURL(file);

            preview.style.backgroundImage = "url('" + currentURL + "')";
            preview.style.backgroundSize = "cover";
            preview.style.backgroundPosition = "center";
            preview.textContent = "";
        });
    }

    bindPreview("#coverImage", "#coverPreview");
    bindPreview("#profileImage", "#profilePreview");

    const servicePhoto = $("#servicePhoto");

    if (servicePhoto) {
        servicePhoto.addEventListener("change", () => {
            validImage(servicePhoto);
        });
    }

 

    const phoneInput = $("#businessPhone");

    if (phoneInput) {
        phoneInput.addEventListener("input", () => {
            const d = phoneInput.value.replace(/\D/g, "").slice(0, 11);
            let out = d;

            if (d.length > 10) {
                out = "(" + d.slice(0, 2) + ") " +
                    d.slice(2, 7) + "-" + d.slice(7);
            } else if (d.length > 6) {
                out = "(" + d.slice(0, 2) + ") " +
                    d.slice(2, 6) + "-" + d.slice(6);
            } else if (d.length > 2) {
                out = "(" + d.slice(0, 2) + ") " + d.slice(2);
            } else if (d.length) {
                out = "(" + d;
            }

            phoneInput.value = out;
        });
    }

 

    const zipInput = $("#businessZip");

    if (zipInput) {
        zipInput.addEventListener("input", () => {
            const d = zipInput.value.replace(/\D/g, "").slice(0, 8);

            zipInput.value = d.length > 5
                ? d.slice(0, 5) + "-" + d.slice(5)
                : d;
        });
    }

  

    const stateInput = $("#businessState");

    if (stateInput) {
        stateInput.addEventListener("input", () => {
            stateInput.value = stateInput.value
                .replace(/[^a-zA-Z]/g, "")
                .toUpperCase()
                .slice(0, 2);
        });
    }


    const linkInput = $("#publicBookingLink");
    const copyButton = $("#copyBookingLink");
    const shareButton = $("#shareBookingLink");

    function flashButton(button, text) {
        if (!button) return;

        const original = button.textContent;
        button.textContent = text;

        setTimeout(() => {
            button.textContent = original;
        }, 2000);
    }

    async function copyLink() {
        if (!linkInput || !copyButton) return;

        const value = linkInput.value;

        try {
            await navigator.clipboard.writeText(value);
        } catch (error) {
            linkInput.select();

            const copied = document.execCommand("copy");

            if (!copied) {
                alert("Não foi possível copiar o link.");
                return;
            }
        }

        flashButton(copyButton, "Copiado!");
    }

    if (linkInput && copyButton) {
        copyButton.addEventListener("click", copyLink);

        linkInput.addEventListener("focus", () => {
            linkInput.select();
        });
    }

    if (linkInput && shareButton) {
        shareButton.addEventListener("click", async () => {
            const name =
                (window.ADMIN_CONFIG &&
                    window.ADMIN_CONFIG.businessName) ||
                "Meu espaço";

            if (navigator.share) {
                try {
                    await navigator.share({
                        title: name,
                        text: "Agende seu horário em " + name,
                        url: linkInput.value
                    });
                } catch (error) {
                    /
            } else {
                await copyLink();
            }
        });
    }

})();
