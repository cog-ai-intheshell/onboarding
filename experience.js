const countdown = document.querySelector(".pilot-countdown");

if (countdown) {
  const deadline = new Date(countdown.dataset.deadline).getTime();
  const fields = {
    days: countdown.querySelector("[data-countdown-days]"),
    hours: countdown.querySelector("[data-countdown-hours]"),
    minutes: countdown.querySelector("[data-countdown-minutes]"),
    seconds: countdown.querySelector("[data-countdown-seconds]"),
  };
  const status = countdown.querySelector("[data-countdown-status]");
  let timer;

  const display = (field, value) => {
    fields[field].textContent = String(value).padStart(2, "0");
  };

  const updateCountdown = () => {
    const remaining = deadline - Date.now();

    if (!Number.isFinite(deadline) || remaining <= 0) {
      Object.keys(fields).forEach((field) => display(field, 0));
      countdown.classList.add("is-expired");
      status.textContent = "L’offre pilote est maintenant clôturée.";
      window.clearInterval(timer);
      return;
    }

    const totalSeconds = Math.floor(remaining / 1000);
    display("days", Math.floor(totalSeconds / 86400));
    display("hours", Math.floor((totalSeconds % 86400) / 3600));
    display("minutes", Math.floor((totalSeconds % 3600) / 60));
    display("seconds", totalSeconds % 60);
  };

  updateCountdown();
  if (Number.isFinite(deadline) && deadline > Date.now()) {
    timer = window.setInterval(updateCountdown, 1000);
  }
}
