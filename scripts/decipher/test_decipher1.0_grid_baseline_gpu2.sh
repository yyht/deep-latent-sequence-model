#!/bin/bash
#SBATCH --gres=gpu:1
#SBATCH --mem=12g
##SBATCH --nodelist=compute-0-7
#SBATCH -t 0

export PYTHONPATH="$(pwd)"
export CUDA_VISIBLE_DEVICES="2"

declare -a arr=("5" "1" "10")

for i in "${arr[@]}"
do
  CUDA_VISIBLE_DEVICES=$1 python src/main.py \
    --dataset decipher1_0 \
    --clean_mem_every 5 \
    --reset_output_dir \
    --classifier_dir="pretrained_classifer/decipher" \
    --data_path data/test/ \
    --train_src_file data/yelp_decipher/yelp_decipher1.0/train.txt \
    --train_trg_file data/yelp_decipher/yelp_decipher1.0/train.attr \
    --dev_src_file data/yelp_decipher/yelp_decipher1.0/dev.txt \
    --dev_trg_file data/yelp_decipher/yelp_decipher1.0/dev.attr \
    --dev_trg_ref data/yelp_decipher/yelp_decipher1.0/dev_ref.txt \
    --src_vocab  data/yelp_decipher/yelp_decipher1.0/text.vocab \
    --trg_vocab  data/yelp_decipher/yelp_decipher1.0/attr.vocab \
    --d_word_vec=128 \
    --d_model=512 \
    --log_every=100 \
    --eval_every=3000 \
    --ppl_thresh=10000 \
    --eval_bleu \
    --batch_size 32 \
    --valid_batch_size 128 \
    --patience 5 \
    --lr_dec 0.8 \
    --lr 0.001 \
    --dropout 0.3 \
    --max_len 10000 \
    --seed 0 \
    --beam_size 1 \
    --word_blank 0.2 \
    --word_dropout 0.1 \
    --word_shuffle 3 \
    --cuda \
    --anneal_epoch 2 \
    --temperature 0.01 \
    --max_pool_k_size $i \
    --bt \
    --gumbel_softmax \
    # --bt_stop_grad \
    # --lm \
    # --avg_len \
    # --gs_soft \
done
