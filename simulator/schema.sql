CREATE SCHEMA IF NOT EXISTS simulation;

CREATE TABLE IF NOT EXISTS simulation.conversation (
    conversation_id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    transcript JSONB NOT NULL CHECK (jsonb_typeof(transcript) = 'object'),
    is_used BOOLEAN NOT NULL DEFAULT FALSE,
    next_conversation UUID REFERENCES simulation.conversation(conversation_id),
    CHECK (next_conversation IS NULL OR next_conversation <> conversation_id)
);
