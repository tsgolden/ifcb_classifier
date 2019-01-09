#! /usr/bin/env python

## Builtin Imports ##
import os
import time
import itertools
from pprint import pprint

## 3rd party library imports ##
import numpy as np
from sklearn.metrics import confusion_matrix, f1_score
from matplotlib.figure import Figure

## TORCH STUFF ##
import torch
import torchvision
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from torchvision import transforms, datasets
from tensorboardX import SummaryWriter
import torchvision.models as MODEL_MODULE

YMD_HMS = "%Y-%m-%d %H:%M:%S"

### UTILITIES ###

# average dimensions of images
from statistics import mean
def calc_avg_dimensions(imagefolder_dataset):
    sizes = [img[0].size for img in imagefolder_dataset]
    x, y = zip(*sizes)
    print('width avg:', mean(x))
    print('height avg:', mean(y))
    print('both avg:', mean(x+y))

#print('Training:')
#calc_avg_dimensions(datasets.ImageFolder(root=train_root))
#print('Testing:')
#calc_avg_dimensions(datasets.ImageFolder(root=test_root))

# only had to do this once. this was with 50:50 data
results = '''
Training:
    width avg: 243.51
    height avg: 85.19
    both avg:  164.35
Testing:
    width avg: 243.81
    height avg: 85.80
    both avg:  164.81
'''


def training_progressbar(batch: int, batches: int, epoch: int, epochs: int,
                         batches_per_dot: int = 1, batches_per_summary: int = 70):

    if batch%batches_per_summary == batches_per_summary-1 or batch==0:
        phase_percent_done = 100*batch/batches
        total_percent_done = 100*(batches*epoch+batch)/(batches*epochs)
        print('\n[ {:1.1f} %] epoch {:<2} Training {:1.1f}% complete'.format(total_percent_done, epoch,
                                                                             phase_percent_done), end=' ', flush=True)

    if batch%batches_per_dot == batches_per_dot-1:
        print('.', end='')


def testing_progressbar(batch: int, batches: int, batches_per_dot: int = 1, batches_per_summary: int = 85):
    if batch%batches_per_summary == batches_per_summary-1 or batch==0:
        phase_percent_done = 100*batch/batches
        print('\nVerification {:1.1f}% complete'.format(phase_percent_done), end=' ', flush=True)

    if batch%batches_per_dot == batches_per_dot-1:
        print('.', end='')


def print_accuracy_dict(accu_dict):
    sorted_accu_list = sorted([(v, k) for k, v in accu_dict.items()], reverse=True)
    for v, k in sorted_accu_list:
        print('{:>26}   {:>2.0f} %   {:<70} |'.format(k, 100*v, '*'*int(70*v)))


def ts2secs(ts1, ts2):
    #_start_time = time.strftime(YMD_HMS)
    #_elapsed_secs = ts2secs(_start_clock, _train_clock)
    t2 = time.mktime(time.strptime(ts2, YMD_HMS))
    t1 = time.mktime(time.strptime(ts1, YMD_HMS))
    return t2-t1


def make_confusion_matrix_plot(true_labels, predict_labels, labels=None, title='Confusion matrix', normalize=False):
    """
    Parameters:
        true_labels                  : These are your true classification categories.
        predict_labels                  : These are you predicted classification categories
        labels                          : This is a lit of labels which will be used to display the axix labels
        title='Confusion matrix'        : Title for your matrix
        normalize=False                 : assumedly, it normalizes the output for classes or different lengths

    Returns: a matplotlib confusion matrix figure
    inspired from https://stackoverflow.com/a/48030258
    """

    # creation of confusion matrix
    if labels is None:
        labels = sorted(list(set(true_labels)))
    cm = confusion_matrix(true_labels, predict_labels, labels=labels)
    if normalize:
        cm = cm.astype('float')*10/cm.sum(axis=1)[:, np.newaxis]
        cm = np.nan_to_num(cm, copy=True)
        cm = cm.astype('int')

    # creation of the plot
    np.set_printoptions(precision=2)

    fig = Figure(figsize=(4.5, 4.5), dpi=320, facecolor='w', edgecolor='k')
    ax = fig.add_subplot(1, 1, 1)
    im = ax.imshow(cm, cmap='Oranges')

    tick_marks = np.arange(len(labels))

    ax.set_xlabel('Predicted Output Classes', fontsize=7)
    ax.set_xticks(tick_marks)
    c = ax.set_xticklabels(labels, fontsize=3, rotation=-90, ha='center')
    ax.xaxis.set_label_position('bottom')
    ax.xaxis.tick_bottom()

    ax.set_ylabel('True Input Classes', fontsize=7)
    ax.set_yticks(tick_marks)
    ax.set_yticklabels(labels, fontsize=3, va='center')
    ax.yaxis.set_label_position('left')
    ax.yaxis.tick_left()

    for i, j in itertools.product(range(cm.shape[0]), range(cm.shape[1])):
        ax.text(j, i, format(cm[i, j], 'd') if cm[i, j] != 0 else '.', horizontalalignment="center", fontsize=2,
                verticalalignment='center', color="black")
    fig.set_tight_layout(True)

    return fig


## TRAINING AND VALIDATING ##


def training_loop(model, training_loader, testing_loader, epochs, logger, device, epoch0=0, optimizer=None, savepath=None, best_loss=float('inf')):
    num_o_batches = len(training_loader)
    best_epoch = epoch0
    best_f1 = 0
    print('Training... there are {} batches per epoch'.format(num_o_batches))
    print('Starting at epoch {} of {}'.format(epoch0+1, epochs))

    # defining loss function
    criterion = nn.CrossEntropyLoss().to(device)

    training_startime = time.strftime(YMD_HMS)
    for epoch in range(epoch0+1,epochs+1):
        model.train()
        epoch_startime = time.strftime(YMD_HMS)
        epoch_loss = 0

        #Process data batch
        for i, data in enumerate(training_loader, 0):
            # send data to gpu(s)
            inputs, labels = data
            inputs, labels = inputs.to(device), labels.to(device)

            # zero the parameter gradients
            optimizer.zero_grad()

            # run model and determin loss
            try:
                outputs = model(inputs).to(device)
                loss = criterion(outputs, labels)
            except: # inception_v3 aux_logits=True
                outputs, aux_outputs = model(inputs)
                outputs, aux_outputs = outputs.to(device), aux_outputs.to(device)
                loss1 = criterion(outputs, labels)
                loss2 = criterion(aux_outputs, labels)
                loss = loss1+0.4*loss2

            # train model
            loss.backward()
            optimizer.step()

            # batch stats
            epoch_loss += loss.item()

            # batch LOGGING
            logger.add_scalar('TRAINING Loss', loss, num_o_batches*epoch+i)
            training_progressbar(i, num_o_batches, epoch, epochs, 2, 140)

        # per epoch VERIFICATION
        verified = verification_loop(model, testing_loader, device)  # dict keys are: loss, accuracy, perclass_accuracy, perclass_correct, perclass_totals, true_inputs, predicted_outputs, classes

        # Saving the model
        if savepath and verified['loss'] < best_loss:
            state = dict(epoch=epoch,
                         model=model.state_dict(),
                         optimizer=optimizer.state_dict(),
                         f1=verified['f1_avg'],
                         validation_loss=verified['loss'])
            torch.save(state, savepath)

            savedir_name = os.path.basename(os.path.dirname(savepath))
            state_txt = dict(epoch=epoch,
                             name = savedir_name,
                             f1=verified['f1_avg'],
                             validation_loss=verified['loss'],
                             secs_elapsed=ts2secs(training_startime, time.strftime(YMD_HMS)),
                             perclass_f1=verified['perclass_f1'])
            with open(os.path.join(os.path.dirname(savepath),savedir_name+'.best.txt'),'w') as f:
                f.write(str(state_txt))

        # epoch LOGGING
        try: firstloss_training == firstloss_verification  # any statement really
        except UnboundLocalError:
            firstloss_training = epoch_loss
            firstloss_verification = verified['loss']

        normalized_training_loss = 100*epoch_loss/firstloss_training
        normalized_verification_loss = 100*verified['loss']/firstloss_verification

        logger.add_scalars('Epoch loss', {'Training': epoch_loss,
                                          'Verification': verified['loss']}, epoch)
        logger.add_scalars('Normalized Epoch loss', {'Training': normalized_training_loss,
                                                     'Verification': normalized_verification_loss}, epoch)
        logger.add_scalars('Accuracy', {'Overall':verified['accuracy'],'F1 Avg':100*verified['f1_avg']}, epoch)
        logger.add_scalars('F1 per class', verified['perclass_f1'], epoch)
        #logger.add_scalars('Accuracy per class', verified['perclass_accuracy'], epoch)

        confusion_matrix_figure = make_confusion_matrix_plot(verified['true_inputs'], verified['predicted_outputs'], normalize=False)
        logger.add_figure('Confusion Matrix', confusion_matrix_figure, epoch)

        now = time.strftime(YMD_HMS)
        epoch_elapsed = ts2secs(epoch_startime, now)
        total_elapsed = ts2secs(training_startime, now)
        output_string = '\nEpoch {} done in {:.0f} mins. loss = {:.3f}. F1 = {:.1f}%. Total elapsed time={:.2f} hrs'
        print(output_string.format(epoch,            epoch_elapsed/60,
                                   verified['loss'], 100*verified['f1_avg'],
                                   total_elapsed/(60*60)) )

        # note or record best epoch, or stop early
        if best_epoch != epoch:
            print('Best Epoch was {} with a validation loss of {:.3f} and an F1 score of {:.1f}%'.format(best_epoch,best_loss,100*best_f1))
        if best_loss > verified['loss']:
            best_loss = verified['loss']
            best_epoch = epoch
            best_f1 = verified['f1_avg']
        elif epoch > 1.33*best_epoch and epoch > 16:
            print("Model probably won't be improving more from here, shutting this operation down")
            return


def verification_loop(model, testing_loader, device):
    """ returns dict of: accuracy, loss, perclass_accuracy, perclass_correct, perclass_totals,
                         true_inputs, predicted_outputs, f1_avg, perclass_f1, classes )"""
    classes = testing_loader.dataset.classes
    indexclass_dict = {i:c for i,c in  enumerate(classes)}

    sum_correct,sum_total,sum_loss = 0,0,0
    class_correct, class_predicted, class_total = [0 for c in classes],[0 for c in classes],[0 for c in classes]
    list_true,list_predicted = [],[]

    model.eval()
    with torch.no_grad():
        criterion = nn.CrossEntropyLoss().to(device)
        for i, data in enumerate(testing_loader, 0):

            # forward pass
            inputs, true_labels = data
            inputs, true_labels = inputs.to(device), true_labels.to(device)

            # run model and determin loss
            try:
                outputs = model(inputs).to(device)
                loss = criterion(outputs, true_labels)
            except: # inception_v3 aux_logits=True
                outputs, aux_outputs = model(inputs)
                outputs, aux_outputs = outputs.to(device), aux_outputs.to(device)
                loss1 = criterion(outputs, true_labels)
                loss2 = criterion(aux_outputs, true_labels)
                loss = loss1+0.4*loss2

            sum_loss += loss.item()

            _, predicted = torch.max(outputs, 1)
            # outputs format is a tensor list of lists, inside lists are len(classes) long,
            # each with a per-class percent prediction. outide list is batch_size long.
            # doing torch.max returns the index of the highest per-class prediction (inside list),
            # for all elements of outside list. Therefor len(predicted)==len(output)==batch_size
            correct = (predicted == true_labels).squeeze()
            # (predicted == true_labels) is a tensor comparison, not a boolean comparison.
            # It does an element-wise comparison where equal values are represented with 1s, and nonequality with 0s
            # So it's a list where matching index values are 1

            # overall percent correct
            sum_total += true_labels.size(0)
            sum_correct += correct.sum().item()

            # per class percent correct
            for j,label in enumerate(true_labels):
                class_correct[label] += correct[j].item()
                class_total[label] += 1
                #class_predicted[label] += predicted[j].item()
                #print('    j={:02}, label={}, pass/fail={}, class_correct[{}]={}/{}'.format(j,label,correct[j].item(),label,class_correct[label],class_total[label]))

            # predicted and true_labels represent classes as numbers, 0-n for n classes.
            # for the confusion matrix we will save these in persistent lists as full class string names
                list_true.append(      indexclass_dict[ int(label) ])
                list_predicted.append( indexclass_dict[ predicted[j].item() ])

            # printing progress
            testing_progressbar(i, len(testing_loader))

    # Overall Accuracy
    overall_accuracy = 100*sum_correct/sum_total
    overall_f1 = f1_score(list_true, list_predicted,average='weighted')
    perclass_f1_list = list(f1_score(list_true, list_predicted,average=None))

    # Accuracy data struct TODO format for confusion matrix
    perclass_accuracy,perclass_f1 = {},{}
    for i in range(len(classes)):
        perclass_accuracy[classes[i]] = class_correct[i]/class_total[i]
        perclass_f1[classes[i]] = perclass_f1_list[i]

    return dict(accuracy=overall_accuracy, loss=sum_loss,
                perclass_accuracy=perclass_accuracy,
                perclass_correct=class_correct,
                perclass_totals=class_total,
                true_inputs=list_true,
                predicted_outputs=list_predicted,
                f1_avg=overall_f1,
                perclass_f1=perclass_f1,
                classes=classes)


## INITIALIZATION ##

import subprocess, argparse

if __name__ == '__main__':
    model_choices = ['inception_v3', 'alexnet','squeezenet',
                     'vgg11','vgg11_bn','vgg13','vgg13_bn','vgg16','vgg16_bn','vgg19','vgg19_bn',
                     'resnet18','resnet34','resnet50','resnet101','resnet151',
                     'densenet121','densenet169','densenet161','densenet201']

    ## Parsing command line input ##
    parser = argparse.ArgumentParser()
    parser.add_argument("training_dir", help="path to training set images")
    parser.add_argument("testing_dir", help="path to testing set images")
    #parser.add_argument("job_id", help="id of sbatch job")
    #parser.add_argument("job_name", help="name of sbatch job")
    parser.add_argument("output_dir", help="directory out output logs and saved model")
    parser.add_argument("--epochs", default=60, type=int, help="How many epochs to run (default 60).\nTraining may end before <epochs> if validation loss keeps rising beyond best_epoch*1.33")
    parser.add_argument("--batch-size", default=108, type=int, dest='batch_size',
                        help="how many images to process in a batch, (default 108, a number divisible by 1,2,3,4 to ensure even batch distribution across up to 4 GPUs)")
    parser.add_argument("--resume", default=False, nargs='?', const=True, help="path to a previously saved model to pick up from (defaults to <output_dir>)")
    parser.add_argument("--model", default='inception_v3', choices=model_choices, help="select a model. some models will override --image-size. (default to inceptin_v3)")
    parser.add_argument("--pretrained", default=False, action='store_true', help='Preloads model with weights trained on imagenet')
    parser.add_argument("--freeze-layers", default=None, type=int, help='freezes layers 0-n of model. assumes --pretrained or --resume. (default None)')
    #parser.add_argument("--image-size",default=224,type=int, dest='image_size',help="scales images to n-by-n pixels (default: 224)")
    #parser.add_argument("--no-save",default=False,action="store_true",dest="no_save", help="if True, a model will not be saved under <output_dir> (default: False)")
    #parser.add_argument("--letterbox",default=False,action='store_true')
    # see https://github.com/laurent-dinh/pylearn/blob/master/pylearn2/utils/image.py find:letterbox
    #parser.add_argument("--verbose",'-v', action="store_true", help="printout epoch dot progressions", default=False)
    #parser.add_argument("--config", help="path to specific ini config file for model and transforms transforms, (default invception_v3)")
    args = parser.parse_args()  # auto sys.argv included

    # input cleanup
    if not args.output_dir.startswith('output/'):
        args.output_dir = 'output/'+args.output_dir
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)
    if not args.training_dir.startswith('data/'):
        args.training_dir = 'data/'+args.training_dir
    if not args.testing_dir.startswith('data/'):
        args.testing_dir = 'data/'+args.testing_dir

    print("Output directory: {}".format(args.output_dir))
    print("pyTorch VERSION:", torch.__version__)

    ## gpu torch setup ##
    if torch.cuda.is_available():
        gpus = [int(gpu) for gpu in os.environ['CUDA_VISIBLE_DEVICES'].split(',')]
        # pytorch keys off the ~index~ of CUDA_VISIBLE_DEVICES.
        # So if gpus == [3,4] then device "cuda:0" == GPU no. 3
        #                      and device "cuda:1" == GPU no. 4
        device = torch.device('cuda:0')
        currdev = torch.cuda.current_device()
    else:
        gpus = []
        device = torch.device("cpu")
        currdev = None
    print("CUDA_VISIBLE_DEVICES: {}".format(gpus))
    print("Active Device is {} (aka torch.cuda.current_device() == {} )".format(device, currdev))


    ## data info ##
    training_numOfiles = subprocess.check_output('find {} -type f | wc -l'.format(args.training_dir),
                                                 shell=True).decode().strip()
    testing_numOfiles = subprocess.check_output('find {} -type f | wc -l'.format(args.testing_dir),
                                                shell=True).decode().strip()
    training_dirSize = subprocess.check_output('du --apparent-size -sh {}'.format(args.training_dir),
                                               shell=True).decode().strip()
    testing_dirSize = subprocess.check_output('du --apparent-size -sh {}'.format(args.testing_dir),
                                              shell=True).decode().strip()
    print("Training Set: {} ({} files, {})".format(args.training_dir, training_numOfiles, training_dirSize))
    print("Testing Set: {} ({} files, {})".format(args.testing_dir, testing_numOfiles, testing_dirSize))

    # setting model appropriate resize
    if args.model == 'inception_v3': pixels = [299,299]
    else: pixels = [224,224]

    ## initializing data ##
    tforms = [transforms.Resize(pixels),  # 299x299 is minimum size for inception
              transforms.ToTensor()]
    tforms = transforms.Compose(tforms)
    training_loader = datasets.ImageFolder(root=args.training_dir, transform=tforms)
    training_loader = torch.utils.data.DataLoader(training_loader, shuffle=True, batch_size=args.batch_size,
                                                  pin_memory=True, num_workers=4)
    testing_loader = datasets.ImageFolder(root=args.testing_dir, transform=tforms)
    testing_loader = torch.utils.data.DataLoader(testing_loader, shuffle=True, batch_size=args.batch_size,
                                                 pin_memory=True, num_workers=4)
    training_len, testing_len = len(training_loader), len(testing_loader)
    assert training_loader.dataset.classes == testing_loader.dataset.classes
    num_o_classes = len(training_loader.dataset.classes)
    print("Number of Classes:", num_o_classes)
    print('RESUME:',args.resume)

    ## initializing model model  ##
    # options:
    # inception_v3, alexnet, squeezenet,
    # vgg11, vgg11_bn, vgg13, vgg13_bn, vgg16, vgg16_bn, vgg19, vgg19_bn,
    # resnet18, resnet34, resnet50, resnet101, resnet151,
    # densenet121, densenet169, densenet161, densenet201

    if args.model == 'inception_v3':
        model = MODEL_MODULE.inception_v3(args.pretrained) #, num_classes=num_o_classes, aux_logits=False)
        model.fc = nn.Linear(model.fc.in_features, num_o_classes)
        model.AuxLogits.fc = nn.Linear(model.AuxLogits.fc.in_features, num_o_classes)
    elif args.model == 'alexnet':
        model = getattr(MODEL_MODULE, args.model)(args.pretrained)
        model.classifier[6] = nn.Linear(model.classifier[6].in_features,num_o_classes)
    elif args.model == 'squeezenet':
        model = getattr(MODEL_MODULE, args.model+'1_1')(args.pretrained)
        model.classifier[1] = nn.Conv2d(512, num_o_classes, kernel_size=(1,1), stride=(1,1))
        model.num_classes = num_o_classes
    elif args.model.startswith('vgg'):
        model = getattr(MODEL_MODULE, args.model)(args.pretrained)
        model.classifier[6] = nn.Linear(model.classifier[6].in_features,num_o_classes)
    elif args.model.startswith('resnet'):
        model = getattr(MODEL_MODULE, args.model)(args.pretrained)
        model.fc = nn.Linear(model.fc.in_features, num_o_classes)
    elif args.model.startswith('densenet'):
        model = getattr(MODEL_MODULE, args.model)(args.pretrained)
        model.classifier = nn.Linear(model.classifier.in_features,num_o_classes)

    if torch.cuda.device_count() > 1:  # if multiple-gpu's detected, use available gpu's
        model = nn.DataParallel(model, device_ids=list(range(len(gpus))))
    model.to(device)  # sends model to GPU

    # freeze layers todo untested
    # https://spandan-madan.github.io/A-Collection-of-important-tasks-in-pytorch/
    try:
        num_o_layers = len(list(model.children()))
        for i,child in enumerate(model.children()):
            if i > args.freeze_layers: break
            print('Freezing layer [{}/{}]: {}'.format(i, num_o_layers, child.__class__))
            for param in child.parameters():
                param.requires_grad = False
    except TypeError as e:
        if 'NoneType' in str(e): print(args.freeze_layers) ;pass # for when args.freeze_layers == None
        else: raise e

    # optimizer
    optimizer = optim.SGD(filter(lambda p: p.requires_grad, model.parameters()), lr=0.001, momentum=0.9)

    # load a previously saved model if one exists, if --resume enabled, otherwise use defaults
    epoch0,best_loss = 0,float('inf')
    if isinstance(args.resume,str):
        model_loadpath = args.resume
    else: model_loadpath = '{}/model.state'.format(args.output_dir)
    if args.resume:
        try:
            savestate = torch.load(model_loadpath)
            model.load_state_dict(savestate['model'])
            optimizer.load_state_dict(savestate['optimizer'])
            epoch0 = savestate['epoch']
            best_loss=savestate['validation_loss']
            print('loading saved model:',model_loadpath)
            # todo: more testing of argparse inputs, and printing of loaded vars
            # todo attempt layer-freeze here as per args.freeze_layers
        except FileNotFoundError as e:
            print(e)

    print("Model: {}".format(model.__class__))
    print("Transformations: {}".format(tforms))
    print("Epochs: {}, Batch size: {}".format(args.epochs, args.batch_size))
    model_savepath = '{}/model.state'.format(args.output_dir)

    ## initializing logger ##
    logger = SummaryWriter(args.output_dir)

    training_loop(model, training_loader, testing_loader, args.epochs, logger, device, epoch0=epoch0,
                  optimizer=optimizer, savepath=model_savepath, best_loss=best_loss)




