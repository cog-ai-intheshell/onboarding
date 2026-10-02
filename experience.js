const experienceContainer = document.querySelector("#experience-content");
const experienceLoading = document.querySelector("#experience-loading");

loadExperienceContent();

async function loadExperienceContent() {
  try {
    let response = await fetch("/api/experience-content", { cache: "no-store" });
    let data = await response.json();
    if (!response.ok || !data.content) {
      response = await fetch("/experience.json", { cache: "no-store" });
      data = { content: await response.json() };
    }
    renderExperienceContent(data.content);
  } catch {
    experienceLoading.innerHTML = '<p class="loading-error">La présentation est momentanément indisponible.</p>';
  }
}

function renderExperienceContent(content) {
  experienceContainer.replaceChildren();

  const introduction = document.createElement("section");
  introduction.className = "text-introduction";
  const label = document.createElement("p");
  label.className = "text-page__label";
  label.textContent = content.label;
  introduction.appendChild(label);
  content.intro.forEach((text) => introduction.appendChild(createParagraph(text)));
  experienceContainer.appendChild(introduction);

  content.sections.forEach((section) => {
    const element = document.createElement("section");
    element.className = `text-section${section.type === "outcomes" ? " text-outcomes" : ""}`;
    const title = document.createElement("h2");
    title.textContent = section.title;
    element.appendChild(title);

    if (section.type === "text") {
      section.paragraphs.forEach((text) => element.appendChild(createParagraph(text)));
    } else if (section.type === "list") {
      const list = document.createElement("ul");
      section.items.forEach((text) => {
        const item = document.createElement("li");
        item.textContent = text;
        list.appendChild(item);
      });
      element.appendChild(list);
    } else if (section.type === "outcomes") {
      section.items.forEach((item) => {
        const itemTitle = document.createElement("h3");
        itemTitle.textContent = item.title;
        element.append(itemTitle, createParagraph(item.text));
      });
    }
    experienceContainer.appendChild(element);
  });

  const footer = document.createElement("footer");
  footer.className = "text-page__footer";
  footer.appendChild(createParagraph(content.footer));
  const link = document.createElement("a");
  link.href = "/";
  link.textContent = "Retour à l’accueil";
  footer.appendChild(link);
  experienceContainer.appendChild(footer);
}

function createParagraph(text) {
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  return paragraph;
}
