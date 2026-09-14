--
-- PostgreSQL database dump
--

\restrict 2oHQW4gNvgzcszvffOMdcl3p2V3gu326GR6XVMdcrJvF7hcbqjXe2JdpQJAfxwq

-- Dumped from database version 16.15 (Debian 16.15-1.pgdg13+2)
-- Dumped by pg_dump version 16.15 (Debian 16.15-1.pgdg13+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: abonnement; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.abonnement (
    id integer NOT NULL,
    entreprise_id integer NOT NULL,
    type_plan character varying(50) NOT NULL,
    date_debut date,
    date_fin date,
    montant numeric(10,2),
    statut character varying(30) DEFAULT 'en_attente'::character varying NOT NULL
);


--
-- Name: abonnement_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.abonnement_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: abonnement_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.abonnement_id_seq OWNED BY public.abonnement.id;


--
-- Name: document_kyc; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_kyc (
    id integer NOT NULL,
    entreprise_id integer NOT NULL,
    type_document character varying(30) NOT NULL,
    nom_fichier character varying(255) NOT NULL,
    date_soumission timestamp without time zone DEFAULT now()
);


--
-- Name: document_kyc_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.document_kyc_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: document_kyc_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.document_kyc_id_seq OWNED BY public.document_kyc.id;


--
-- Name: entreprise; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entreprise (
    id integer NOT NULL,
    type_compte character varying(20) DEFAULT 'entreprise'::character varying NOT NULL,
    nom character varying(150) NOT NULL,
    secteur character varying(100),
    identifiant_unique character varying(50) NOT NULL,
    nom_base character varying(100) NOT NULL,
    statut character varying(20) DEFAULT 'en_attente'::character varying NOT NULL,
    email_contact character varying(150) NOT NULL,
    telephone_contact character varying(30),
    date_creation timestamp without time zone DEFAULT now(),
    conditions_acceptees_le timestamp without time zone,
    conditions_version character varying(20),
    numero_identification_fiscale character varying(50),
    numero_cin character varying(30),
    cgu_accepte_le timestamp without time zone,
    cgu_version character varying(20),
    numero_fiscal character varying(50)
);


--
-- Name: entreprise_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.entreprise_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: entreprise_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.entreprise_id_seq OWNED BY public.entreprise.id;


--
-- Name: journal_audit; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.journal_audit (
    id integer NOT NULL,
    entreprise_id integer,
    acteur character varying(150),
    action character varying(150) NOT NULL,
    details text,
    date_action timestamp without time zone DEFAULT now()
);


--
-- Name: journal_audit_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.journal_audit_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: journal_audit_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.journal_audit_id_seq OWNED BY public.journal_audit.id;


--
-- Name: licence; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.licence (
    id integer NOT NULL,
    entreprise_id integer NOT NULL,
    type_licence character varying(50) NOT NULL,
    nb_utilisateurs_max integer,
    date_expiration date
);


--
-- Name: licence_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.licence_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: licence_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.licence_id_seq OWNED BY public.licence.id;


--
-- Name: parametre_global; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.parametre_global (
    id integer NOT NULL,
    cle character varying(100) NOT NULL,
    valeur text
);


--
-- Name: parametre_global_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.parametre_global_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: parametre_global_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.parametre_global_id_seq OWNED BY public.parametre_global.id;


--
-- Name: super_admin; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.super_admin (
    id integer NOT NULL,
    nom character varying(100) NOT NULL,
    email character varying(150) NOT NULL,
    mot_de_passe character varying(255) NOT NULL,
    date_creation timestamp without time zone DEFAULT now()
);


--
-- Name: super_admin_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.super_admin_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: super_admin_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.super_admin_id_seq OWNED BY public.super_admin.id;


--
-- Name: abonnement id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.abonnement ALTER COLUMN id SET DEFAULT nextval('public.abonnement_id_seq'::regclass);


--
-- Name: document_kyc id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_kyc ALTER COLUMN id SET DEFAULT nextval('public.document_kyc_id_seq'::regclass);


--
-- Name: entreprise id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entreprise ALTER COLUMN id SET DEFAULT nextval('public.entreprise_id_seq'::regclass);


--
-- Name: journal_audit id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.journal_audit ALTER COLUMN id SET DEFAULT nextval('public.journal_audit_id_seq'::regclass);


--
-- Name: licence id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.licence ALTER COLUMN id SET DEFAULT nextval('public.licence_id_seq'::regclass);


--
-- Name: parametre_global id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parametre_global ALTER COLUMN id SET DEFAULT nextval('public.parametre_global_id_seq'::regclass);


--
-- Name: super_admin id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.super_admin ALTER COLUMN id SET DEFAULT nextval('public.super_admin_id_seq'::regclass);


--
-- Data for Name: abonnement; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.abonnement (id, entreprise_id, type_plan, date_debut, date_fin, montant, statut) FROM stdin;
1	2	essai	\N	\N	\N	actif
\.


--
-- Data for Name: document_kyc; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.document_kyc (id, entreprise_id, type_document, nom_fichier, date_soumission) FROM stdin;
1	2	cin_gerant	Capture d'écran 2025-11-23 001523.png	2026-09-10 20:24:51.296148
2	2	patente	Capture d'écran 2025-11-23 001523.png	2026-09-10 20:24:51.296148
3	2	extrait_rne	Capture d'écran 2025-11-23 001523.png	2026-09-10 20:24:51.296148
\.


--
-- Data for Name: entreprise; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.entreprise (id, type_compte, nom, secteur, identifiant_unique, nom_base, statut, email_contact, telephone_contact, date_creation, conditions_acceptees_le, conditions_version, numero_identification_fiscale, numero_cin, cgu_accepte_le, cgu_version, numero_fiscal) FROM stdin;
1	entreprise	BENJEDDOU	Distribution	FB85D511	compte_benjeddou_fb85d511	en_attente	test.ben09@gmail.com	0612345679	2026-09-10 20:09:10.657804	\N	\N	\N	ab12345	2026-09-10 20:09:10.656139	v1	1234567
2	entreprise	BENJEDDOU	Distrubution	32586FAF	compte_benjeddou_32586faf	actif	test.test@gmail.com	0612345678	2026-09-10 20:22:34.730724	\N	\N	\N	AB12345	2026-09-10 20:22:34.730283	v1	32145
\.


--
-- Data for Name: journal_audit; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.journal_audit (id, entreprise_id, acteur, action, details, date_action) FROM stdin;
\.


--
-- Data for Name: licence; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.licence (id, entreprise_id, type_licence, nb_utilisateurs_max, date_expiration) FROM stdin;
\.


--
-- Data for Name: parametre_global; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.parametre_global (id, cle, valeur) FROM stdin;
\.


--
-- Data for Name: super_admin; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.super_admin (id, nom, email, mot_de_passe, date_creation) FROM stdin;
\.


--
-- Name: abonnement_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.abonnement_id_seq', 1, true);


--
-- Name: document_kyc_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.document_kyc_id_seq', 3, true);


--
-- Name: entreprise_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.entreprise_id_seq', 2, true);


--
-- Name: journal_audit_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.journal_audit_id_seq', 1, false);


--
-- Name: licence_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.licence_id_seq', 1, false);


--
-- Name: parametre_global_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.parametre_global_id_seq', 1, false);


--
-- Name: super_admin_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.super_admin_id_seq', 1, false);


--
-- Name: abonnement abonnement_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.abonnement
    ADD CONSTRAINT abonnement_pkey PRIMARY KEY (id);


--
-- Name: document_kyc document_kyc_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_kyc
    ADD CONSTRAINT document_kyc_pkey PRIMARY KEY (id);


--
-- Name: entreprise entreprise_identifiant_unique_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entreprise
    ADD CONSTRAINT entreprise_identifiant_unique_key UNIQUE (identifiant_unique);


--
-- Name: entreprise entreprise_nom_base_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entreprise
    ADD CONSTRAINT entreprise_nom_base_key UNIQUE (nom_base);


--
-- Name: entreprise entreprise_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entreprise
    ADD CONSTRAINT entreprise_pkey PRIMARY KEY (id);


--
-- Name: journal_audit journal_audit_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.journal_audit
    ADD CONSTRAINT journal_audit_pkey PRIMARY KEY (id);


--
-- Name: licence licence_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.licence
    ADD CONSTRAINT licence_pkey PRIMARY KEY (id);


--
-- Name: parametre_global parametre_global_cle_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parametre_global
    ADD CONSTRAINT parametre_global_cle_key UNIQUE (cle);


--
-- Name: parametre_global parametre_global_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parametre_global
    ADD CONSTRAINT parametre_global_pkey PRIMARY KEY (id);


--
-- Name: super_admin super_admin_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.super_admin
    ADD CONSTRAINT super_admin_email_key UNIQUE (email);


--
-- Name: super_admin super_admin_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.super_admin
    ADD CONSTRAINT super_admin_pkey PRIMARY KEY (id);


--
-- Name: abonnement abonnement_entreprise_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.abonnement
    ADD CONSTRAINT abonnement_entreprise_id_fkey FOREIGN KEY (entreprise_id) REFERENCES public.entreprise(id) ON DELETE CASCADE;


--
-- Name: document_kyc document_kyc_entreprise_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_kyc
    ADD CONSTRAINT document_kyc_entreprise_id_fkey FOREIGN KEY (entreprise_id) REFERENCES public.entreprise(id) ON DELETE CASCADE;


--
-- Name: journal_audit journal_audit_entreprise_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.journal_audit
    ADD CONSTRAINT journal_audit_entreprise_id_fkey FOREIGN KEY (entreprise_id) REFERENCES public.entreprise(id) ON DELETE SET NULL;


--
-- Name: licence licence_entreprise_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.licence
    ADD CONSTRAINT licence_entreprise_id_fkey FOREIGN KEY (entreprise_id) REFERENCES public.entreprise(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict 2oHQW4gNvgzcszvffOMdcl3p2V3gu326GR6XVMdcrJvF7hcbqjXe2JdpQJAfxwq

