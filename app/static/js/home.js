const constBtn = document.querySelector(".hero-cta-button");
const constBtnMob = document.querySelector(".m-btn");

constBtn.addEventListener("click", () => {
  window.location.href = "/constructor";
});

constBtnMob.addEventListener("click", () => {
  window.location.href = "/constructor";
});

const value = `; ${document.cookie}`;
const parts = value.split(`; visits=`);

const visitCount = parts.length === 2 ? parts.pop().split(";").shift() : 0;
if (visitCount)
  window.alert(`You have visited this page ${visitCount} time(s)`);
