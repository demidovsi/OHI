-- Метаданные документов, загруженных в бакет (форма «Документы», documents.py).
-- Выполняется один раз администратором БД (схема ohi). Файлы лежат в бакете DOCS_BUCKET (по умолчанию ohi-docs),
-- в таблице — только сведения о них. Таблица не зарегистрирована в метаданных MDM (форма «Классы» modeler_web): веб
-- работает с ней напрямую через v2/execute; при необходимости её можно зарегистрировать там как класс documents.

create table if not exists ohi.nsi_documents (
    id            serial primary key,
    sh_name       varchar(300) not null,           -- имя файла
    blob_name     varchar(500) not null unique,    -- путь объекта в бакете (documents/ГГГГ/ММ/<id>_<имя>)
    bucket        varchar(100) not null,           -- бакет
    content_type  varchar(150),
    size          bigint       not null,           -- размер, байт
    sha256        char(64)     not null unique,    -- контрольная сумма: один и тот же файл повторно не загружается
    description   text,
    uploaded_by   varchar(200),                    -- кто загрузил
    inserted_date timestamp without time zone not null default (now() at time zone 'utc')
);

create index if not exists nsi_documents_inserted_date_idx on ohi.nsi_documents (inserted_date);

comment on table ohi.nsi_documents is 'Документы в бакете (метаданные)';
