import type { Locale } from "./locales";

export interface Dictionary {
  nav: { documents: string; analytics: string; crawlStatus: string; language: string };
  documents: {
    title: string;
    filterSection: string;
    filterStatus: string;
    allSections: string;
    allStatuses: string;
    empty: string;
    originalLink: string;
    comments: string;
    noComments: string;
    pageOf: (page: number) => string;
    prevPage: string;
    nextPage: string;
    createdDate: string;
    discussionEndDate: string;
    reactions: string;
    untitled: string;
  };
  analytics: {
    title: string;
    bySection: string;
    byStatus: string;
    timeseries: string;
    day: string;
    week: string;
    other: string;
    count: string;
    date: string;
  };
  crawlStatus: {
    title: string;
    lastProcessedAt: string;
    never: string;
    recentErrors: string;
    noErrors: string;
    pageType: string;
    status: string;
    count: string;
    url: string;
    error: string;
    processedAt: string;
  };
  errors: {
    genericTitle: string;
    genericBody: string;
    retry: string;
    notFoundTitle: string;
    notFoundBody: string;
  };
}

const ru: Dictionary = {
  nav: { documents: "Документы", analytics: "Аналитика", crawlStatus: "Статус обхода", language: "Язык" },
  documents: {
    title: "Документы",
    filterSection: "Раздел",
    filterStatus: "Статус",
    allSections: "Все разделы",
    allStatuses: "Все статусы",
    empty: "Документы не найдены",
    originalLink: "Оригинал на legalacts.egov.kz",
    comments: "Комментарии",
    noComments: "Комментариев нет",
    pageOf: (page) => `Страница ${page}`,
    prevPage: "Назад",
    nextPage: "Вперёд",
    createdDate: "Дата создания",
    discussionEndDate: "Дата окончания обсуждения",
    reactions: "Лайки / дизлайки",
    untitled: "Без названия",
  },
  analytics: {
    title: "Аналитика",
    bySection: "Документы по разделам",
    byStatus: "Документы по статусам",
    timeseries: "Динамика по датам",
    day: "По дням",
    week: "По неделям",
    other: "Прочее",
    count: "Количество",
    date: "Дата",
  },
  crawlStatus: {
    title: "Статус обхода",
    lastProcessedAt: "Последняя обработка",
    never: "ещё не было",
    recentErrors: "Последние ошибки",
    noErrors: "Ошибок нет",
    pageType: "Тип страницы",
    status: "Статус",
    count: "Количество",
    url: "URL",
    error: "Ошибка",
    processedAt: "Обработано",
  },
  errors: {
    genericTitle: "Что-то пошло не так",
    genericBody: "Не удалось получить данные с сервера. Попробуйте ещё раз.",
    retry: "Повторить",
    notFoundTitle: "Страница не найдена",
    notFoundBody: "Запрошенная страница или документ не существует.",
  },
};

const kk: Dictionary = {
  nav: { documents: "Құжаттар", analytics: "Аналитика", crawlStatus: "Аралау мәртебесі", language: "Тіл" },
  documents: {
    title: "Құжаттар",
    filterSection: "Бөлім",
    filterStatus: "Мәртебе",
    allSections: "Барлық бөлімдер",
    allStatuses: "Барлық мәртебелер",
    empty: "Құжаттар табылмады",
    originalLink: "legalacts.egov.kz сайтындағы түпнұсқа",
    comments: "Пікірлер",
    noComments: "Пікірлер жоқ",
    pageOf: (page) => `${page}-бет`,
    prevPage: "Артқа",
    nextPage: "Алға",
    createdDate: "Құрылған күні",
    discussionEndDate: "Талқылау аяқталу күні",
    reactions: "Лайк / дизлайк",
    untitled: "Атауы жоқ",
  },
  analytics: {
    title: "Аналитика",
    bySection: "Бөлімдер бойынша құжаттар",
    byStatus: "Мәртебелер бойынша құжаттар",
    timeseries: "Күндер бойынша динамика",
    day: "Күн бойынша",
    week: "Апта бойынша",
    other: "Басқа",
    count: "Саны",
    date: "Күн",
  },
  crawlStatus: {
    title: "Аралау мәртебесі",
    lastProcessedAt: "Соңғы өңдеу",
    never: "әлі болған жоқ",
    recentErrors: "Соңғы қателер",
    noErrors: "Қателер жоқ",
    pageType: "Бет түрі",
    status: "Мәртебе",
    count: "Саны",
    url: "URL",
    error: "Қате",
    processedAt: "Өңделді",
  },
  errors: {
    genericTitle: "Бірдеңе дұрыс болмады",
    genericBody: "Сервермен байланыс болмады. Қайталап көріңіз.",
    retry: "Қайталау",
    notFoundTitle: "Бет табылмады",
    notFoundBody: "Сұралған бет немесе құжат жоқ.",
  },
};

const dictionaries: Record<Locale, Dictionary> = { ru, kk };

export function getDictionary(locale: Locale): Dictionary {
  return dictionaries[locale];
}
