
const CONFIG = {
    whatsapp: "5547999999999",

    openingHours: {
        0: null, 
        1: { start: "09:00", end: "18:00" },
        2: { start: "09:00", end: "18:00" },
        3: { start: "09:00", end: "18:00" },
        4: { start: "09:00", end: "18:00" },
        5: { start: "09:00", end: "18:00" },
        6: { start: "09:00", end: "13:00" }
    },


    interval: 10,


    blockedTimes: [],


    blockedDates: [],

   
    bookedTimes: []
};

const steps = {
    procedure: document.getElementById("step-procedure"),
    date: document.getElementById("step-date"),
    customer: document.getElementById("step-customer"),
    confirmation: document.getElementById("step-confirmation")
};

const progressSteps = document.querySelectorAll(".progress-step");

const calendarMonth = document.getElementById("calendar-month");
const calendarDays = document.getElementById("calendar-days");

const previousMonthButton = document.getElementById("prev-month");
const nextMonthButton = document.getElementById("next-month");

const timeSlots = document.getElementById("time-slots");

const bookingForm = document.getElementById("booking-form");
const confirmButton = document.getElementById("confirm-booking");

const booking = {
    service: null,
    price: 0,
    duration: 0,
    date: null,
    time: null,
    name: "",
    phone: "",
    notes: ""
};

let currentMonth = new Date();
currentMonth.setDate(1);

function formatCurrency(value) {
    return Number(value).toLocaleString("pt-BR", {
        style: "currency",
        currency: "BRL"
    });
}

function formatDate(dateString) {
    if (!dateString) return "-";

    const [year, month, day] = dateString.split("-");

    return `${day}/${month}/${year}`;
}

function getLocalDateString(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");

    return `${year}-${month}-${day}`;
}

function timeToMinutes(time) {
    const [hours, minutes] = time.split(":").map(Number);

    return hours * 60 + minutes;
}

function minutesToTime(minutes) {
    const hours = Math.floor(minutes / 60);
    const remainingMinutes = minutes % 60;

    return (
        String(hours).padStart(2, "0") +
        ":" +
        String(remainingMinutes).padStart(2, "0")
    );
}

function formatDuration(minutes) {
    const hours = Math.floor(minutes / 60);
    const remaining = minutes % 60;

    if (hours && remaining) {
        return `${hours}h ${remaining}min`;
    }

    if (hours) {
        return `${hours}h`;
    }

    return `${remaining} minutos`;
}

const stepOrder = [
    "procedure",
    "date",
    "customer",
    "confirmation"
];

function showStep(stepName) {

    if (!steps[stepName]) return;

    Object.values(steps).forEach(step => {
        step.hidden = true;
    });

    steps[stepName].hidden = false;

    const currentIndex = stepOrder.indexOf(stepName);

    progressSteps.forEach((step, index) => {

        step.classList.toggle(
            "active",
            index <= currentIndex
        );

    });

    const bookingSection = document.getElementById("agendamento");

    bookingSection.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });

}


const serviceButtons = document.querySelectorAll(
    ".booking-service"
);

const serviceCardButtons = document.querySelectorAll(
    ".service-select"
);

function selectService(button) {

    booking.service = button.dataset.service;
    booking.price = Number(button.dataset.price);
    booking.duration = Number(button.dataset.duration);

    serviceButtons.forEach(item => {
        item.classList.toggle(
            "selected",
            item.dataset.service === booking.service
        );
    });

    serviceCardButtons.forEach(item => {
        item.classList.toggle(
            "selected",
            item.dataset.service === booking.service
        );
    });

}

serviceButtons.forEach(button => {

    button.addEventListener("click", () => {
        selectService(button);
    });

});

serviceCardButtons.forEach(button => {

    button.addEventListener("click", () => {

        selectService(button);

        showStep("date");

        renderCalendar();

    });

});

document.querySelectorAll(".booking-next").forEach(button => {

    button.addEventListener("click", () => {

        const nextStep = button.dataset.next;

        if (nextStep === "date") {

            if (!booking.service) {
                alert("Selecione um procedimento antes de continuar.");
                return;
            }

            showStep("date");
            renderCalendar();

        }

        if (nextStep === "customer") {

            if (!booking.date) {
                alert("Selecione uma data.");
                return;
            }

            if (!booking.time) {
                alert("Selecione um horário.");
                return;
            }

            showStep("customer");

        }

    });

});


document.querySelectorAll(".booking-back").forEach(button => {

    button.addEventListener("click", () => {

        const previousStep = button.dataset.back;

        showStep(previousStep);

    });

});

const monthNames = [
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro"
];

function renderCalendar() {

    if (!calendarDays || !calendarMonth) return;

    calendarDays.innerHTML = "";

    const year = currentMonth.getFullYear();
    const month = currentMonth.getMonth();

    const firstDay = new Date(year, month, 1).getDay();

    const lastDay = new Date(year, month + 1, 0).getDate();

    calendarMonth.textContent =
        `${monthNames[month]} ${year}`;

    // Espaços antes do primeiro dia
    for (let i = 0; i < firstDay; i++) {

        const empty = document.createElement("div");

        empty.className = "empty-day";

        calendarDays.appendChild(empty);

    }

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    for (let day = 1; day <= lastDay; day++) {

        const date = new Date(year, month, day);

        const dateString = getLocalDateString(date);

        const button = document.createElement("button");

        button.type = "button";
        button.textContent = day;

        const weekday = date.getDay();

        const isPast = date < today;

        const isClosed = !CONFIG.openingHours[weekday];

        const isBlocked = CONFIG.blockedDates.includes(dateString);

        const unavailable = isPast || isClosed || isBlocked;

        button.disabled = unavailable;

        if (booking.date === dateString) {
            button.classList.add("selected");
        }

        if (!unavailable) {

            button.addEventListener("click", () => {

                booking.date = dateString;
                booking.time = null;

                renderCalendar();
                renderAvailableTimes();

            });

        }

        calendarDays.appendChild(button);

    }

}

previousMonthButton.addEventListener("click", () => {

    const today = new Date();

    const previous = new Date(
        currentMonth.getFullYear(),
        currentMonth.getMonth() - 1,
        1
    );

    const current = new Date(
        today.getFullYear(),
        today.getMonth(),
        1
    );

    if (previous < current) return;

    currentMonth = previous;

    renderCalendar();

});

nextMonthButton.addEventListener("click", () => {

    currentMonth = new Date(
        currentMonth.getFullYear(),
        currentMonth.getMonth() + 1,
        1
    );

    renderCalendar();

});


function isTimeBlocked(date, time, duration) {

    const start = timeToMinutes(time);
    const end = start + duration;

    const booked = CONFIG.bookedTimes.some(item => {

        if (item.date !== date) return false;

        const bookedStart = timeToMinutes(item.time);
        const bookedEnd = bookedStart + duration;

        return start < bookedEnd && end > bookedStart;

    });

    if (booked) return true;

    const blocked = CONFIG.blockedTimes.some(item => {

        if (item.date !== date) return false;

        const blockedStart = timeToMinutes(item.start);
        const blockedEnd = timeToMinutes(item.end);

        return start < blockedEnd && end > blockedStart;

    });

    if (blocked) return true;

    const today = getLocalDateString(new Date());

    if (date === today) {

        const now = new Date();

        const currentMinutes =
            now.getHours() * 60 + now.getMinutes();

        if (start <= currentMinutes) return true;

    }

    return false;

}


function renderAvailableTimes() {

    timeSlots.innerHTML = "";

    if (!booking.date) return;

    const [year, month, day] = booking.date.split("-").map(Number);

    const weekday = new Date(year, month - 1, day).getDay();

    const hours = CONFIG.openingHours[weekday];

    if (!hours) {

        timeSlots.textContent = "Não há atendimento nesta data.";

        return;

    }

    const start = timeToMinutes(hours.start);
    const end = timeToMinutes(hours.end);

    const step = 10;

    let availableCount = 0;

    for (
        let time = start;
        time + booking.duration <= end;
        time += step
    ) {

        const formattedTime = minutesToTime(time);

        if (
            isTimeBlocked(
                booking.date,
                formattedTime,
                booking.duration
            )
        ) {
            continue;
        }

        const button = document.createElement("button");

        button.type = "button";
        button.textContent = formattedTime;

        if (booking.time === formattedTime) {
            button.classList.add("selected");
        }

        button.addEventListener("click", () => {

            booking.time = formattedTime;

            renderAvailableTimes();

        });

        timeSlots.appendChild(button);

        availableCount++;

    }

    if (availableCount === 0) {

        timeSlots.textContent =
            "Não existem horários disponíveis nesta data.";

    }

}



bookingForm.addEventListener("submit", event => {

    event.preventDefault();

    if (!booking.service || !booking.date || !booking.time) {

        alert("Verifique o procedimento, a data e o horário.");

        return;

    }

    booking.name =
        document.getElementById("customer-name").value.trim();

    booking.phone =
        document.getElementById("customer-phone").value.trim();

    booking.notes =
        document.getElementById("customer-notes").value.trim();

    if (!booking.name || !booking.phone) {

        alert("Preencha seu nome e telefone.");

        return;

    }

    showSummary();

    showStep("confirmation");

});


function showSummary() {

    document.getElementById("summary-service").textContent =
        booking.service;

    document.getElementById("summary-price").textContent =
        formatCurrency(booking.price);

    document.getElementById("summary-duration").textContent =
        formatDuration(booking.duration);

    document.getElementById("summary-date").textContent =
        formatDate(booking.date);

    document.getElementById("summary-time").textContent =
        booking.time;

    document.getElementById("summary-name").textContent =
        booking.name;

    document.getElementById("summary-phone").textContent =
        booking.phone;

}



confirmButton.addEventListener("click", () => {

    if (
        !CONFIG.whatsapp ||
        CONFIG.whatsapp === "5547999999999"
    ) {

        alert(
            "Configure o número de WhatsApp da profissional no script.js."
        );

        return;

    }

    const message = `
Olá! Gostaria de solicitar um agendamento.

*Nome:* ${booking.name}

*Telefone:* ${booking.phone}

*Procedimento:* ${booking.service}

*Preço:* ${formatCurrency(booking.price)}

*Duração:* ${formatDuration(booking.duration)}

*Data:* ${formatDate(booking.date)}

*Horário:* ${booking.time}

*Observações:* ${booking.notes || "Nenhuma"}

Aguardo a confirmação do meu horário. Obrigada!
    `.trim();

    const whatsappURL =
        `https://wa.me/${CONFIG.whatsapp}?text=${encodeURIComponent(message)}`;

    window.open(
        whatsappURL,
        "_blank",
        "noopener,noreferrer"
    );

});

const animatedElements = document.querySelectorAll(
    ".section-title, .service-card, .details-grid > div"
);

if ("IntersectionObserver" in window) {

    const observer = new IntersectionObserver(
        (entries, observerInstance) => {

            entries.forEach(entry => {

                if (entry.isIntersecting) {

                    entry.target.classList.add("visible");

                    observerInstance.unobserve(entry.target);

                }

            });

        },
        {
            threshold: 0.12
        }
    );

    animatedElements.forEach(element => {

        element.classList.add("reveal");

        observer.observe(element);

    });

}




document.getElementById("current-year").textContent =
    new Date().getFullYear();



renderCalendar();



(function () {
    function normalizar(texto) {
        return (texto || "")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .trim()
            .toLowerCase();
    }

    document.querySelectorAll(".service-select").forEach(function (botao) {
        botao.addEventListener("click", function () {
            var nome = normalizar(botao.dataset.service);
            var secao = document.getElementById("agendamento");

            var alvo = Array.from(document.querySelectorAll(".booking-service"))
                .find(function (item) {
                    return normalizar(item.dataset.service) === nome;
                });

            if (secao) {
                secao.scrollIntoView({ behavior: "smooth", block: "start" });
            }

            if (!alvo) {
                
                return;
            }

            alvo.click(); 

            var continuar = document.querySelector('.booking-next[data-next="date"]');
            if (continuar) {
                continuar.click(); 
            }
        });
    });
})();

