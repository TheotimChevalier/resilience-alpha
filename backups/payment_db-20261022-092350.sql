--
-- PostgreSQL database dump
--

\restrict ePq482a1aHRdvU70igF3ebb3lI3wmui2VTd30yq3r3Nyio6OQraVR4u1MnKirmT

-- Dumped from database version 15.19
-- Dumped by pg_dump version 15.19

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

DROP INDEX IF EXISTS public.ix_transactions_user_id;
DROP INDEX IF EXISTS public.ix_transactions_id;
ALTER TABLE IF EXISTS ONLY public.transactions DROP CONSTRAINT IF EXISTS transactions_pkey;
ALTER TABLE IF EXISTS public.transactions ALTER COLUMN id DROP DEFAULT;
DROP SEQUENCE IF EXISTS public.transactions_id_seq;
DROP TABLE IF EXISTS public.transactions;
SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: transactions; Type: TABLE; Schema: public; Owner: resilience
--

CREATE TABLE public.transactions (
    id integer NOT NULL,
    user_id character varying NOT NULL,
    amount double precision NOT NULL,
    status character varying NOT NULL
);


ALTER TABLE public.transactions OWNER TO resilience;

--
-- Name: transactions_id_seq; Type: SEQUENCE; Schema: public; Owner: resilience
--

CREATE SEQUENCE public.transactions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.transactions_id_seq OWNER TO resilience;

--
-- Name: transactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: resilience
--

ALTER SEQUENCE public.transactions_id_seq OWNED BY public.transactions.id;


--
-- Name: transactions id; Type: DEFAULT; Schema: public; Owner: resilience
--

ALTER TABLE ONLY public.transactions ALTER COLUMN id SET DEFAULT nextval('public.transactions_id_seq'::regclass);


--
-- Data for Name: transactions; Type: TABLE DATA; Schema: public; Owner: resilience
--

COPY public.transactions (id, user_id, amount, status) FROM stdin;
\.


--
-- Name: transactions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: resilience
--

SELECT pg_catalog.setval('public.transactions_id_seq', 1, false);


--
-- Name: transactions transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: resilience
--

ALTER TABLE ONLY public.transactions
    ADD CONSTRAINT transactions_pkey PRIMARY KEY (id);


--
-- Name: ix_transactions_id; Type: INDEX; Schema: public; Owner: resilience
--

CREATE INDEX ix_transactions_id ON public.transactions USING btree (id);


--
-- Name: ix_transactions_user_id; Type: INDEX; Schema: public; Owner: resilience
--

CREATE INDEX ix_transactions_user_id ON public.transactions USING btree (user_id);


--
-- PostgreSQL database dump complete
--

\unrestrict ePq482a1aHRdvU70igF3ebb3lI3wmui2VTd30yq3r3Nyio6OQraVR4u1MnKirmT

